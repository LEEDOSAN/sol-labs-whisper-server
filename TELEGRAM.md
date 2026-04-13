# SOL LABS AI 텔레그램 업무관리 봇

## 봇 정보
- 봇 이름: @sollabsai_bot
- 서버: Railway (sol-labs-whisper-server)
- 데이터 저장: Railway Volume /data/

## 역할 체계
- CEO: 모든 권한 (TELEGRAM_ADMIN_ID 자동 지정)
- Developer: 내 업무 관리
- CMO: 내 업무 관리
- 🐝 여왕벌: 내 업무 관리
- Member: 내 업무 관리

## 환경변수
- TELEGRAM_BOT_TOKEN: 봇 토큰
- TELEGRAM_ADMIN_ID: CEO 텔레그램 ID
- ANTHROPIC_API_KEY: Claude API 키
- DATA_DIR=/data: Railway Volume 경로

## 데이터 파일
- /data/tasks.json: 업무 데이터 + 유저 정보
- /data/users.json: 언어 설정 + 대화 상태

## 구현된 기능
- 버튼 UI (인라인 키보드)
- 역할별 메뉴 분리
- 개인 DM 방식
- 4개 언어 지원 (한/영/러/우즈벡)
- 업무 등록/수정/담당자변경/검색
- 진행률 업데이트 (% 진행바)
- 우선순위 설정 (긴급/일반/낮음)
- 마감일 자동 알림 (매일 9시 KST)
- 개인 DM 업무 현황 (매일 10시 KST)
- 지연 업무 자동 정리 (3일 초과)
- 주간 보고서 (매주 월요일 9시 KST)
- 월간 통계
- 사용법 안내 (역할별)

## 주요 명령어
- /menu: 메인 메뉴
- /debug: 데이터 확인 (CEO 전용)
- /resetroles: 역할 초기화 (CEO 전용)

## 개발 규칙
- 신규 기능 추가 시 TELEGRAM.md 업데이트 필수
- 4개 언어 번역 항상 포함
- 기존 /transcribe, /analyze 엔드포인트 절대 건드리지 말 것
