# SOL LABS AI — Whisper 서버
음성 파일 청크 분할 + OpenAI Whisper 처리 전용 서버.

## 환경변수
- OPENAI_API_KEY
- RAILWAY_API_KEY

## 엔드포인트
- GET /health
- POST /transcribe

## 성능
- 1시간 파일 기준 약 4분 처리
- Whisper 청크 병렬 처리
- 최대 2시간 파일 지원 (200MB)
