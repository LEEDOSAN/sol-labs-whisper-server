# SOL LABS AI — Whisper 서버

## 역할
Vercel에서 처리 불가능한 대용량 음성 파일 처리 전담.
25MB 초과 파일을 Vercel에서 이 서버로 위임.

## 처리 흐름
1. Vercel → Blob URL 전달
2. Blob URL에서 파일 다운로드
3. ffmpeg으로 20분 단위 청크 분할
4. ThreadPoolExecutor로 Whisper 병렬 처리
5. 결과 합쳐서 Vercel로 반환

## 성능
- 1시간 파일: 약 1.4분 (Whisper 처리)
- 최대 지원: 2시간 / 200MB

## 환경변수
- OPENAI_API_KEY
- RAILWAY_API_KEY

## 엔드포인트
- GET /health → {"status": "ok"}
- POST /transcribe → 음성 처리
