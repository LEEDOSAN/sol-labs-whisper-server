# Whisper Server 작업 기록

## WhisperX 롤백 (2026-04-05)

### 롤백 이유
- WhisperX 도입 시도 (커밋 ac96edc ~ a18b13b)
- Railway 메모리 제한으로 large-v3 → medium 다운그레이드 시도
- PyAV 빌드 실패 (pkg-config, FFmpeg 개발 패키지 부족)
- Dockerfile에 gcc, build-essential 등 추가했으나 의존성 충돌 지속
- whisperx 버전 다운그레이드(3.3.1 → 3.1.1)도 해결 안 됨
- **결론: WhisperX는 Railway 서버리스 환경에 부적합. OpenAI Whisper API 방식으로 롤백**

### 롤백 범위
- main.py: WhisperX → OpenAI Whisper API (청크 병렬 처리) 복원
- requirements.txt: whisperx, pyannote, torch 등 제거, openai 패키지 복원
- Dockerfile: 빌드 도구 제거, ffmpeg만 유지

### 향후 참고
- WhisperX는 GPU + 충분한 메모리 환경에서만 사용 가능
- Railway 환경에서는 OpenAI Whisper API 호출 방식이 안정적
- 발화자 구분이 필요하면 별도 diarization API 검토 필요
