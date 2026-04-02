import os
import glob
import subprocess
import tempfile
import requests as req
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from openai import OpenAI

app = FastAPI()

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
RAILWAY_API_KEY = os.environ.get("RAILWAY_API_KEY")

CHUNK_DURATION = 1200  # 20분(초)


class TranscribeRequest(BaseModel):
    blob_url: str
    file_name: str
    api_key: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transcribe")
def transcribe(body: TranscribeRequest):
    # 1. API 키 검증
    if body.api_key != RAILWAY_API_KEY:
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

        # 5-6. 각 청크 Whisper API 전송 + 결과 합치기
        client = OpenAI(api_key=OPENAI_API_KEY)
        full_transcript = ""
        all_segments = []

        for idx, chunk_path in enumerate(chunk_files):
            offset = idx * CHUNK_DURATION

            with open(chunk_path, "rb") as audio:
                result = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio,
                    language="ko",
                    response_format="verbose_json",
                )

            full_transcript += result.text

            if result.segments:
                for seg in result.segments:
                    all_segments.append(
                        {
                            "start": round(seg["start"] + offset, 2),
                            "end": round(seg["end"] + offset, 2),
                            "text": seg["text"],
                        }
                    )

        # 8. 결과 반환
        return {
            "transcript": full_transcript,
            "segments": all_segments,
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
