import os
import re
import json
import glob
import uuid
import asyncio
import subprocess
import tempfile
import concurrent.futures
from datetime import datetime, timedelta
import requests as req
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from openai import OpenAI
import anthropic

app = FastAPI()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
RAILWAY_API_KEY = os.environ.get("RAILWAY_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

CHUNK_DURATION = 1200  # 20분(초)

# ─────────────────────────────────────────────────────────
# 비동기 job 저장소 (in-memory dict)
# /analyze는 즉시 job_id를 반환하고 백그라운드로 분석 진행
# /job-status/{job_id}로 상태/결과 조회
# 재시작 시 모든 pending job 소실 (단순 구현)
# ─────────────────────────────────────────────────────────
# 구조: { job_id: { status: 'pending'|'completed'|'failed',
#                   result?: dict, error?: str, created_at: datetime } }
jobs: dict[str, dict] = {}
JOB_TTL_SECONDS = 3600  # 1시간 후 만료


def cleanup_old_jobs():
    """만료된 job 정리 (lazy cleanup — status 조회 시 호출)"""
    now = datetime.utcnow()
    expired = [
        jid
        for jid, j in jobs.items()
        if now - j.get("created_at", now) > timedelta(seconds=JOB_TTL_SECONDS)
    ]
    for jid in expired:
        jobs.pop(jid, None)


class TranscribeRequest(BaseModel):
    blob_url: str
    file_name: str
    # api_key는 더 이상 본문으로 받지 않음 (헤더 X-Railway-Key 사용)
    # 구버전 클라이언트 호환을 위해 Optional로 유지
    api_key: str | None = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe")
def transcribe(body: TranscribeRequest, request: Request):
    # 1. API 키 검증 — 헤더 우선, 없으면 본문 fallback (구버전 호환)
    header_key = request.headers.get("X-Railway-Key")
    provided_key = header_key or body.api_key
    if provided_key != RAILWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    tmp_files: list[str] = []

    try:
        # 2. blob_url에서 파일 다운로드
        resp = req.get(body.blob_url, timeout=300)
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail="파일 다운로드 실패")

        # 3. /tmp에 임시 저장
        suffix = os.path.splitext(body.file_name)[1] or ".m4a"
        input_path = os.path.join(tempfile.gettempdir(), f"input{suffix}")
        with open(input_path, "wb") as f:
            f.write(resp.content)
        tmp_files.append(input_path)

        # 4. ffmpeg 청크 분할 (20분 단위, 16kHz 모노 mp3)
        chunk_pattern = os.path.join(tempfile.gettempdir(), "chunk_%03d.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", input_path,
                "-f", "segment",
                "-segment_time", str(CHUNK_DURATION),
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "libmp3lame",
                chunk_pattern,
            ],
            check=True,
            capture_output=True,
        )

        chunk_files = sorted(
            glob.glob(os.path.join(tempfile.gettempdir(), "chunk_*.mp3"))
        )
        tmp_files.extend(chunk_files)

        if not chunk_files:
            raise HTTPException(status_code=500, detail="청크 분할 실패")

        # 5-6. 각 청크 Whisper API 병렬 전송 + 결과 합치기
        client = OpenAI(api_key=OPENAI_API_KEY)

        def transcribe_chunk(chunk_path: str):
            with open(chunk_path, "rb") as audio:
                return client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language="ko",
                    response_format="verbose_json",
                )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(transcribe_chunk, cp)
                for cp in chunk_files
            ]
            results = [f.result() for f in futures]

        full_transcript = ""
        all_chunk_segments = []
        for result in results:
            full_transcript += result.text
            if result.segments:
                all_chunk_segments.append(result.segments)

        # segments 합치기 (객체 속성 → model_dump 변환)
        segments_combined = []
        offset = 0.0
        for chunk_segments in all_chunk_segments:
            for seg in chunk_segments:
                seg_dict = seg.model_dump() if hasattr(seg, 'model_dump') else dict(seg)
                segments_combined.append({
                    "start": seg_dict["start"] + offset,
                    "end": seg_dict["end"] + offset,
                    "text": seg_dict["text"]
                })
            if chunk_segments:
                last = chunk_segments[-1]
                last_dict = last.model_dump() if hasattr(last, 'model_dump') else dict(last)
                offset += last_dict["end"]

        # 8. 결과 반환
        return {
            "transcript": full_transcript,
            "segments": segments_combined,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 7. /tmp 임시 파일 삭제
        for f in tmp_files:
            try:
                os.remove(f)
            except OSError:
                pass


# ──────────────────────────────────────────
# Claude 회의록 분석 엔드포인트
# ──────────────────────────────────────────

SPEAKER_DETECTION_RULES = """## 발화자 구분 지침 (반드시 준수)
1. 참석자 목록과 직책을 먼저 확인한 후 분석을 시작하세요.
2. [pause Xs] 마커는 발화자 전환 가능성이 높습니다.
3. 직책별 발화 패턴 힌트:
   - 대표/CEO/사장 → 결정, 지시, 방향 제시, 최종 승인
   - 팀장/과장/매니저 → 보고, 제안, 중간 정리, 일정 조율
   - 개발자/엔지니어 → 기술 설명, 구현 방법, 난이도 평가
   - 디자이너 → 시각적 요소, 사용자 경험, UI/UX 관련
4. 대화 중 이름이 직접 언급되면 해당 발화자 또는 다음 응답자를 확정하세요.
5. 질문→답변 패턴으로 발화자를 추정하세요.
6. 발화자 수는 참석자 수 이내로 제한하세요.
7. 불확실해도 가장 가능성 높은 참석자 이름을 사용하세요.
8. 발화 흐름 단위로 묶어서 반환하세요.
9. Whisper segments의 start 값을 Math.round()하여 timeIndex로 사용."""

CHUNK_PROMPT = f"""주어진 회의 대화록 구간을 분석하세요.
반드시 아래 JSON 형식으로만 응답하세요. JSON 외 텍스트는 절대 포함하지 마세요.
Claude AI 대신 SOL LABS AI로 표기하세요. 한국어로 작성하세요.
비용·기간·견적을 추정하지 마세요. 회의에서 실제 언급된 금액·일정만 기록하세요.

{SPEAKER_DETECTION_RULES}

## 이전 구간 발화자 연속성
- 이전 구간에서 식별된 발화자가 전달되면 반드시 같은 이름을 사용하세요.

{{
  "summary": "이 구간 핵심 내용 요약 (3~5문장)",
  "decisions": ["결정사항1"],
  "todos": ["할 일1"],
  "speakers": ["발화자1"],
  "keyTopics": ["주제1"],
  "utterances": [
    {{ "speaker": "발화자명", "text": "발화 내용", "timeIndex": 0 }}
  ]
}}"""

FINAL_PROMPT = f"""당신은 회의록 분석 전문가입니다.
여러 구간별 요약을 종합하여 전체 회의록을 분석하세요.
반드시 아래 JSON 형식으로만 응답하세요. JSON 외 텍스트는 절대 포함하지 마세요.
Claude AI 대신 SOL LABS AI로 표기하세요. 한국어로 작성하세요.
비용·기간·견적을 추정하지 마세요. 회의에서 실제 언급된 금액·일정만 기록하세요.
참석자 정보에 직책이 포함된 경우, 할 일 배정 시 직책을 고려하세요.

## meetingPurpose 작성 규칙
- 반드시 1~2문장으로 작성
- '이 미팅은 ~을 위해 진행됐습니다' 형식

## 요약 우선순위 규칙
### keyDiscussions: 2번+ 반복 → [반복 언급], 시간/날짜 → [일정], 금액 → [금액]
### decisions: 확정된 날짜·금액·기간 반드시 포함
### todos: high=날짜/금액/기간 언급, medium=2번+ 언급, low=1번 언급
### nextActions: 업무 순서대로, 선행 조건은 → 로 연결

{{
  "meetingPurpose": "이 미팅은 ~을 위해 진행됐습니다.",
  "coreTopics": ["주제1", "주제2"],
  "keyDiscussions": [
    {{ "topic": "논의 주제", "content": "상세 내용" }}
  ],
  "decisions": ["결정사항1"],
  "todos": [
    {{ "person": "담당자명", "task": "할 일", "priority": "high|medium|low" }}
  ],
  "nextActions": ["다음 액션1"]
}}"""

SINGLE_PROMPT = f"""당신은 회의록 분석 전문가입니다.
주어진 회의 내용을 분석하여 반드시 아래 JSON 형식으로만 응답하세요.
JSON 외 텍스트는 절대 포함하지 마세요.
Claude AI 대신 SOL LABS AI로 표기하세요. 한국어로 작성하세요.
비용·기간·견적을 추정하지 마세요. 회의에서 실제 언급된 금액·일정만 기록하세요.
참석자 정보에 직책이 포함된 경우, 할 일 배정 시 직책을 고려하세요.

## meetingPurpose 작성 규칙
- 반드시 1~2문장으로 작성
- '이 미팅은 ~을 위해 진행됐습니다' 형식

{SPEAKER_DETECTION_RULES}

## 요약 우선순위 규칙
### keyDiscussions: 2번+ 반복 → [반복 언급], 시간/날짜 → [일정], 금액 → [금액]
### decisions: 확정된 날짜·금액·기간 반드시 포함
### todos: high=날짜/금액/기간 언급, medium=2번+ 언급, low=1번 언급
### nextActions: 업무 순서대로, 선행 조건은 → 로 연결

{{
  "meetingPurpose": "이 미팅은 ~을 위해 진행됐습니다.",
  "coreTopics": ["주제1", "주제2"],
  "keyDiscussions": [
    {{ "topic": "논의 주제", "content": "상세 내용" }}
  ],
  "decisions": ["결정사항1"],
  "todos": [
    {{ "person": "담당자명", "task": "할 일", "priority": "high|medium|low" }}
  ],
  "nextActions": ["다음 액션1"],
  "transcript": "전달받은 전체 대화록 그대로",
  "utterances": [
    {{ "speaker": "발화자명", "text": "발화 내용", "timeIndex": 0 }}
  ]
}}"""


def split_segments_by_time(segments, chunk_seconds=1800):
    """segments를 시간 기준으로 청크 분할 (30분 단위)"""
    if not segments:
        return []
    chunks = []
    current = []
    chunk_start = segments[0].get("start", 0)
    for seg in segments:
        if seg.get("start", 0) - chunk_start >= chunk_seconds and current:
            chunks.append(current)
            current = []
            chunk_start = seg.get("start", 0)
        current.append(seg)
    if current:
        chunks.append(current)
    return chunks


def _run_claude_analysis(body: dict) -> dict:
    """Claude 회의록 분석 본체 — 입력 검증 완료 상태의 body 기준.
    /analyze 엔드포인트와 백그라운드 job worker에서 공통 사용."""
    transcript = body.get("transcript", "")
    segments = body.get("segments", [])
    meeting_title = body.get("meetingTitle", "")
    project_name = body.get("projectName", "")
    attendees = body.get("attendees", [])

    # 대화록 길이 제한
    MAX_TRANSCRIPT = 50000
    full_transcript = transcript[:MAX_TRANSCRIPT] if len(transcript) > MAX_TRANSCRIPT else transcript
    attendees_str = ", ".join(attendees) if attendees else ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # 청크 분할
    segment_chunks = split_segments_by_time(segments) if segments else []

    if len(segment_chunks) >= 2:
        # ── 청크 요약 방식 ──
        chunk_summaries = []
        all_utterances = []
        previous_speakers = []

        for i, chunk in enumerate(segment_chunks):
            start_min = int(chunk[0].get("start", 0) / 60)
            end_min = int(chunk[-1].get("start", 0) / 60) + 1
            chunk_text = " ".join(s.get("text", "").strip() for s in chunk)
            chunk_segs = json.dumps([
                {"start": round(s.get("start", 0), 1), "text": s.get("text", "").strip()}
                for s in chunk
            ], ensure_ascii=False)

            speaker_hint = ""
            if previous_speakers:
                speaker_hint = f"\n이전 구간 발화자: {', '.join(previous_speakers)}\n동일 인물이면 같은 이름 사용."

            chunk_content = f"""미팅 제목: {meeting_title}
{f'참석자: {attendees_str}' if attendees_str else ''}
구간: {start_min}분 ~ {end_min}분 ({i+1}/{len(segment_chunks)}){speaker_hint}

=== 대화록 ===
{chunk_text}

=== Segments ===
{chunk_segs}"""

            try:
                chunk_msg = client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=2000,
                    system=CHUNK_PROMPT,
                    messages=[{"role": "user", "content": chunk_content}],
                )
                raw = chunk_msg.content[0].text if chunk_msg.content[0].type == "text" else ""
                chunk_summaries.append(f"[구간 {i+1}: {start_min}분~{end_min}분]\n{raw}")

                try:
                    match = re.search(r'\{[\s\S]*\}', raw)
                    if match:
                        parsed = json.loads(match.group())
                        if "utterances" in parsed:
                            all_utterances.extend(parsed["utterances"])
                            speakers = [u["speaker"] for u in parsed["utterances"]]
                            previous_speakers = list(set(previous_speakers + speakers))
                except (json.JSONDecodeError, KeyError):
                    pass
            except Exception:
                pass

        # 최종 분석
        final_content = f"""미팅 제목: {meeting_title}
{f'프로젝트명: {project_name}' if project_name else ''}
{f'참석자: {attendees_str}' if attendees_str else ''}

=== 구간별 요약 (총 {len(chunk_summaries)}개 구간) ===

{chr(10).join(chunk_summaries)}"""

        final_msg = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=8000,
            system=FINAL_PROMPT,
            messages=[{"role": "user", "content": final_content}],
        )
        final_raw = final_msg.content[0].text if final_msg.content[0].type == "text" else ""
        final_match = re.search(r'\{[\s\S]*\}', final_raw)
        if not final_match:
            raise RuntimeError("최종 분석 JSON 파싱 실패")

        result = json.loads(final_match.group())
        result["transcript"] = full_transcript
        result["utterances"] = all_utterances
        return result

    # ── 단일 분석 ──
    segments_text = ""
    if segments:
        segments_text = f"\n=== Segments ===\n{json.dumps([{'start': round(s.get('start', 0), 1), 'text': s.get('text', '').strip()} for s in segments], ensure_ascii=False)}"

    user_content = f"""미팅 제목: {meeting_title}
{f'프로젝트명: {project_name}' if project_name else ''}
{f'참석자: {attendees_str}' if attendees_str else ''}

=== 회의 대화록 ===
{full_transcript}{segments_text}"""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=8192,
        system=SINGLE_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    raw_text = message.content[0].text if message.content[0].type == "text" else ""
    json_match = re.search(r'\{[\s\S]*\}', raw_text)
    if not json_match:
        raise RuntimeError("분석 JSON 파싱 실패")

    result = json.loads(json_match.group())
    result["transcript"] = full_transcript
    return result


async def _analysis_worker(job_id: str, body: dict):
    """백그라운드 분석 worker — Claude 호출이 블로킹이므로 thread pool에서 실행.
    완료/실패 시 jobs dict 갱신."""
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, _run_claude_analysis, body)
        if job_id in jobs:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["result"] = result
    except Exception as e:
        if job_id in jobs:
            jobs[job_id]["status"] = "failed"
            jobs[job_id]["error"] = str(e)


@app.post("/analyze")
async def analyze_meeting(request: Request):
    """Claude 회의록 분석 — 비동기 job 기반.
    요청 수신 → job_id 생성 → 백그라운드 분석 시작 → job_id 즉시 반환.
    클라이언트는 /job-status/{job_id}로 진행 상황/결과 조회."""
    body = await request.json()

    # API 키 검증 — 헤더 우선, 없으면 본문 fallback (구버전 호환)
    header_key = request.headers.get("X-Railway-Key")
    api_key = header_key or body.get("api_key", "")
    if api_key != RAILWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=503, detail="Anthropic API 키 미설정")

    if not body.get("transcript") or not body.get("meetingTitle"):
        raise HTTPException(status_code=400, detail="대화록과 미팅 제목은 필수")

    # 만료 job 청소 + 새 job 생성
    cleanup_old_jobs()
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "pending",
        "created_at": datetime.utcnow(),
    }

    # 백그라운드 분석 시작 (fire-and-forget)
    asyncio.create_task(_analysis_worker(job_id, body))

    return {"job_id": job_id, "status": "pending"}


@app.get("/job-status/{job_id}")
def job_status(job_id: str, request: Request):
    """분석 job 상태 조회 — pending/completed/failed 중 하나 반환.
    completed일 때 result 필드 포함, failed일 때 error 필드 포함."""
    # API 키 검증
    header_key = request.headers.get("X-Railway-Key")
    if header_key != RAILWAY_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    cleanup_old_jobs()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found or expired")

    response: dict = {"status": job["status"]}
    if job["status"] == "completed":
        response["result"] = job.get("result")
    elif job["status"] == "failed":
        response["error"] = job.get("error", "Unknown error")
    return response
