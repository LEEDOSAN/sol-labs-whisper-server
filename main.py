import os
import tempfile
import requests as req
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import whisperx

app = FastAPI()

RAILWAY_API_KEY = os.environ.get("RAILWAY_API_KEY")
HF_TOKEN = os.environ.get("HUGGINGFACE_TOKEN")

# WhisperX 모델 (서버 시작 후 첫 요청 시 1회 로딩)
whisper_model = None
align_model = None
align_metadata = None
diarize_model = None


def load_models():
    """WhisperX 모델 전역 로딩 (lazy init)"""
    global whisper_model, align_model, align_metadata, diarize_model
    if whisper_model is None:
        whisper_model = whisperx.load_model(
            "large-v3", device="cpu", compute_type="int8", language="ko"
        )
    if align_model is None:
        align_model, align_metadata = whisperx.load_align_model(
            language_code="ko", device="cpu"
        )
    if diarize_model is None and HF_TOKEN:
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=HF_TOKEN, device="cpu"
        )


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

    # 모델 로딩
    load_models()

    input_path = ""

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

        # 4. WhisperX 음성 인식
        audio = whisperx.load_audio(input_path)
        result = whisper_model.transcribe(audio, batch_size=16)

        # 5. 정렬 (단어 단위 타임스탬프 정밀화)
        result = whisperx.align(
            result["segments"], align_model, align_metadata, audio, device="cpu"
        )

        # 6. 발화자 구분 (diarization)
        if diarize_model:
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)

        # 7. 응답 구성
        segments = []
        full_text = ""
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            segments.append({
                "speaker": seg.get("speaker", "SPEAKER_00"),
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": text,
            })
            full_text += text + " "

        return {
            "transcript": full_text.strip(),
            "segments": segments,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # 임시 파일 삭제
        if input_path:
            try:
                os.remove(input_path)
            except OSError:
                pass
