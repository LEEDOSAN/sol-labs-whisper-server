"""
텔레그램 업무관리 봇 — FastAPI와 같은 프로세스에서 실행
SOL LABS AI 내부 업무 관리용
"""

import os
import json
import re
import asyncio
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from telegram import Update, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# 환경변수
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.environ.get("TELEGRAM_ADMIN_ID")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

# 데이터 파일 경로
TASKS_FILE = Path(__file__).parent / "tasks.json"

# KST 타임존
KST = ZoneInfo("Asia/Seoul")


# ──────────────────────────────────────────
# 데이터 저장/로드
# ──────────────────────────────────────────

def _load_data() -> dict:
    """tasks.json에서 데이터 로드"""
    if TASKS_FILE.exists():
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_id": 1, "users": {}, "tasks": []}


def _save_data(data: dict):
    """tasks.json에 데이터 저장"""
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_group_chat_id(chat_id: int):
    """그룹 채팅방 ID 저장 (자동 알림 전송용)"""
    data = _load_data()
    if "group_chat_ids" not in data:
        data["group_chat_ids"] = []
    cid = str(chat_id)
    if cid not in data["group_chat_ids"]:
        data["group_chat_ids"].append(cid)
        _save_data(data)
        print(f"[telegram-bot] 그룹챗 등록: {chat_id}", flush=True)


def _get_group_chat_ids() -> list[str]:
    """저장된 그룹 채팅방 ID 목록 반환"""
    data = _load_data()
    return data.get("group_chat_ids", [])


def _progress_bar(percent: int) -> str:
    """진행률을 시각적 진행바로 변환"""
    filled = min(percent // 20, 5)
    return "🟩" * filled + "⬜" * (5 - filled)


# ──────────────────────────────────────────
# 번역 관련
# ──────────────────────────────────────────

def _needs_translation(text: str) -> bool:
    """한국어가 아닌 텍스트인지 판별 (러시아어/우즈벡어/영어)"""
    # 키릴 문자 감지 (러시아어/우즈벡어 키릴 표기)
    if re.search(r'[\u0400-\u04FF]', text):
        return True
    # 라틴 문자가 한국어보다 많으면 번역 필요
    korean_chars = len(re.findall(r'[\uAC00-\uD7A3]', text))
    latin_chars = len(re.findall(r'[a-zA-Z]', text))
    if latin_chars > 3 and latin_chars > korean_chars:
        return True
    return False


async def _translate_to_korean(text: str) -> str | None:
    """Claude API로 한국어 번역"""
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=500,
                system="당신은 번역 전문가입니다. 주어진 텍스트를 한국어로 번역하세요. 번역된 텍스트만 출력하세요. 추가 설명 없이.",
                messages=[{"role": "user", "content": text}],
            ),
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[telegram-bot] 번역 실패: {e}", flush=True)
        return None


# ──────────────────────────────────────────
# 업무카드 포맷
# ──────────────────────────────────────────

def _format_task_card(task: dict, users: dict) -> str:
    """업무카드 형식으로 출력"""
    status_emoji = {"대기": "⚪", "진행중": "🟡", "완료": "🟢", "취소": "🔴"}
    emoji = status_emoji.get(task["status"], "⚪")

    # 담당자 역할 찾기
    assignee_role = ""
    for uinfo in users.values():
        if uinfo["name"] == task.get("assignee"):
            assignee_role = f" ({uinfo['role']})"
            break

    # 진행률 진행바 표시
    progress_line = ""
    if task.get("progress") and task["status"] not in ("완료", "취소"):
        progress_line = f"\n진행: {_progress_bar(task['progress'])} {task['progress']}%"

    return (
        f"📋 업무 #{task['id']:03d}\n"
        f"담당: @{task['assignee']}{assignee_role}\n"
        f"내용: {task['content']}\n"
        f"마감: {task['deadline']}\n"
        f"상태: {emoji} {task['status']}{progress_line}\n"
        f"등록자: @{task['creator']}"
    )


# ──────────────────────────────────────────
# 명령어 핸들러
# ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start — 봇 소개"""
    await update.message.reply_text(
        "👋 SOL LABS 업무관리 봇입니다!\n\n"
        "📌 명령어 목록:\n"
        "/register [역할] — 역할 등록 (대표/개발자/마케터/직원)\n"
        "/task @담당자 업무내용 마감일 — 업무 등록\n"
        "/update 업무번호 진행내용 — 진행상황 업데이트\n"
        "/list — 전체 업무 현황\n"
        "/mylist — 내 업무 보기\n"
        "/done 업무번호 — 업무 완료 처리\n"
        "/cancel 업무번호 — 업무 취소\n"
        "/report — 전체 보고서 (대표 전용)"
    )


async def cmd_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/register [역할] — 역할 등록"""
    if not context.args:
        await update.message.reply_text(
            "❌ 사용법: /register [역할]\n"
            "역할: 대표, 개발자, 마케터, 직원"
        )
        return

    role = context.args[0]
    valid_roles = ["대표", "개발자", "마케터", "직원"]
    if role not in valid_roles:
        await update.message.reply_text(
            f"❌ 유효하지 않은 역할이에요.\n사용 가능: {', '.join(valid_roles)}"
        )
        return

    user_id = str(update.effective_user.id)
    user_name = (
        update.effective_user.full_name
        or update.effective_user.username
        or "Unknown"
    )

    data = _load_data()

    # 대표는 최초 1회만 등록 가능
    if role == "대표":
        existing_admin = any(
            u["role"] == "대표" for uid, u in data["users"].items() if uid != user_id
        )
        if existing_admin:
            await update.message.reply_text("❌ 대표 역할은 이미 다른 분이 등록하셨어요.")
            return

    data["users"][user_id] = {
        "name": user_name,
        "role": role,
        "username": update.effective_user.username or "",
    }
    _save_data(data)

    await update.message.reply_text(f"✅ 등록 완료!\n이름: {user_name}\n역할: {role}")


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/task @담당자 업무내용 마감일 — 업무 등록"""
    user_id = str(update.effective_user.id)
    data = _load_data()

    if user_id not in data["users"]:
        await update.message.reply_text("❌ 먼저 /register 로 역할을 등록해주세요.")
        return

    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "❌ 사용법: /task @담당자 업무내용 마감일\n"
            "예시: /task @홍길동 SOL홈페이지 사이드바 구현 2026.04.18"
        )
        return

    # 파싱: 첫 번째 = 담당자, 마지막 = 마감일, 나머지 = 업무내용
    assignee_raw = context.args[0].lstrip("@")
    deadline = context.args[-1]

    # 마감일 형식 검증
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', deadline):
        await update.message.reply_text(
            "❌ 마감일 형식이 올바르지 않아요.\n형식: YYYY.MM.DD (예: 2026.04.18)"
        )
        return

    content = " ".join(context.args[1:-1])
    if not content:
        await update.message.reply_text("❌ 업무 내용을 입력해주세요.")
        return

    # 번역 처리
    translated = None
    if _needs_translation(content):
        translated = await _translate_to_korean(content)

    task_id = data["next_id"]
    creator_name = data["users"][user_id]["name"]

    task = {
        "id": task_id,
        "assignee": assignee_raw,
        "content": translated or content,
        "content_original": content if translated else None,
        "deadline": deadline,
        "status": "대기",
        "progress": 0,
        "creator": creator_name,
        "creator_id": user_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "updates": [],
    }

    data["tasks"].append(task)
    data["next_id"] = task_id + 1
    _save_data(data)

    reply = f"✅ 업무 등록 완료!\n\n{_format_task_card(task, data['users'])}"
    if translated and content != translated:
        reply += f"\n\n[원본] {content}\n[번역] {translated}"

    await update.message.reply_text(reply)


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/update 업무번호 진행내용 — 진행상황 업데이트"""
    user_id = str(update.effective_user.id)
    data = _load_data()

    if user_id not in data["users"]:
        await update.message.reply_text("❌ 먼저 /register 로 역할을 등록해주세요.")
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ 사용법: /update 업무번호 진행내용\n"
            "예시: /update 1 사이드바 80% 완료"
        )
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 업무번호는 숫자로 입력해주세요.")
        return

    update_content = " ".join(context.args[1:])

    # 업무 찾기
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(f"❌ 업무 #{task_id:03d}을 찾을 수 없어요.")
        return

    # 권한 확인: 대표는 전체, 나머지는 본인 업무만
    user_role = data["users"][user_id]["role"]
    user_name = data["users"][user_id]["name"]
    if user_role != "대표" and task["assignee"] != user_name:
        await update.message.reply_text("❌ 본인에게 배정된 업무만 업데이트할 수 있어요.")
        return

    # 번역 처리
    translated = None
    if _needs_translation(update_content):
        translated = await _translate_to_korean(update_content)

    # 진행률 자동 감지 (숫자% 패턴)
    progress_match = re.search(r'(\d+)\s*%', update_content)
    if progress_match:
        task["progress"] = int(progress_match.group(1))
        task["status"] = "진행중"
    elif task["status"] == "대기":
        task["status"] = "진행중"

    task["updates"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "content": translated or update_content,
        "content_original": update_content if translated else None,
        "by": user_name,
    })
    _save_data(data)

    reply = f"✅ 업무 #{task_id:03d} 업데이트 완료!\n\n{_format_task_card(task, data['users'])}"
    if translated and update_content != translated:
        reply += f"\n\n[원본] {update_content}\n[번역] {translated}"

    await update.message.reply_text(reply)


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/list — 전체 업무 현황"""
    data = _load_data()
    tasks = data["tasks"]

    if not tasks:
        await update.message.reply_text("📋 등록된 업무가 없습니다.")
        return

    active = [t for t in tasks if t["status"] not in ("완료", "취소")]
    done = [t for t in tasks if t["status"] == "완료"]
    cancelled = [t for t in tasks if t["status"] == "취소"]

    lines = [f"📋 전체 업무 현황 (총 {len(tasks)}건)\n"]

    if active:
        lines.append("── 진행 중 ──")
        for t in active:
            lines.append(_format_task_card(t, data["users"]))
            lines.append("")

    if done:
        lines.append(f"── 완료 ({len(done)}건) ──")
        for t in done:
            lines.append(_format_task_card(t, data["users"]))
            lines.append("")

    if cancelled:
        lines.append(f"── 취소 ({len(cancelled)}건) ──")
        for t in cancelled:
            lines.append(_format_task_card(t, data["users"]))
            lines.append("")

    # 텔레그램 메시지 길이 제한 (4096자) 대응
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (더 많은 업무가 있어요)"

    await update.message.reply_text(text)


async def cmd_mylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/mylist — 본인 업무만 보기"""
    user_id = str(update.effective_user.id)
    data = _load_data()

    if user_id not in data["users"]:
        await update.message.reply_text("❌ 먼저 /register 로 역할을 등록해주세요.")
        return

    user_name = data["users"][user_id]["name"]
    my_tasks = [t for t in data["tasks"] if t["assignee"] == user_name]

    if not my_tasks:
        await update.message.reply_text("📋 배정된 업무가 없습니다.")
        return

    lines = [f"📋 {user_name}님의 업무 ({len(my_tasks)}건)\n"]
    for t in my_tasks:
        lines.append(_format_task_card(t, data["users"]))
        lines.append("")

    await update.message.reply_text("\n".join(lines))


async def cmd_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/done 업무번호 — 업무 완료 처리"""
    user_id = str(update.effective_user.id)
    data = _load_data()

    if user_id not in data["users"]:
        await update.message.reply_text("❌ 먼저 /register 로 역할을 등록해주세요.")
        return

    if not context.args:
        await update.message.reply_text("❌ 사용법: /done 업무번호\n예시: /done 1")
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 업무번호는 숫자로 입력해주세요.")
        return

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(f"❌ 업무 #{task_id:03d}을 찾을 수 없어요.")
        return

    # 권한 확인
    user_role = data["users"][user_id]["role"]
    user_name = data["users"][user_id]["name"]
    if user_role != "대표" and task["assignee"] != user_name:
        await update.message.reply_text("❌ 본인에게 배정된 업무만 완료 처리할 수 있어요.")
        return

    task["status"] = "완료"
    task["progress"] = 100
    task["updates"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "content": "업무 완료 처리",
        "by": user_name,
    })
    _save_data(data)

    await update.message.reply_text(
        f"🟢 업무 #{task_id:03d} 완료!\n\n{_format_task_card(task, data['users'])}"
    )


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/report — 전체 요약 보고 (대표만 가능)"""
    user_id = str(update.effective_user.id)
    data = _load_data()

    if user_id not in data["users"]:
        await update.message.reply_text("❌ 먼저 /register 로 역할을 등록해주세요.")
        return

    if data["users"][user_id]["role"] != "대표":
        await update.message.reply_text("❌ /report는 대표만 사용할 수 있어요.")
        return

    tasks = data["tasks"]
    if not tasks:
        await update.message.reply_text("📊 등록된 업무가 없습니다.")
        return

    # 통계
    total = len(tasks)
    waiting = len([t for t in tasks if t["status"] == "대기"])
    in_progress = len([t for t in tasks if t["status"] == "진행중"])
    completed = len([t for t in tasks if t["status"] == "완료"])

    # 담당자별 현황
    assignee_stats = {}
    for t in tasks:
        name = t["assignee"]
        if name not in assignee_stats:
            assignee_stats[name] = {"total": 0, "done": 0, "active": 0}
        assignee_stats[name]["total"] += 1
        if t["status"] == "완료":
            assignee_stats[name]["done"] += 1
        else:
            assignee_stats[name]["active"] += 1

    # 마감 임박 업무 (3일 이내)
    today = datetime.now()
    urgent = []
    for t in tasks:
        if t["status"] == "완료":
            continue
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d")
            days_left = (dl - today).days
            if days_left <= 3:
                urgent.append((t, days_left))
        except ValueError:
            pass

    lines = [
        "📊 전체 업무 보고서",
        f"날짜: {today.strftime('%Y.%m.%d')}",
        "",
        f"📈 전체 현황: 총 {total}건",
        f"  ⚪ 대기: {waiting}건",
        f"  🟡 진행중: {in_progress}건",
        f"  🟢 완료: {completed}건",
        f"  완료율: {round(completed / total * 100) if total else 0}%",
        "",
        "👥 담당자별 현황",
    ]

    for name, stats in assignee_stats.items():
        lines.append(
            f"  {name}: 총 {stats['total']}건 "
            f"(진행 {stats['active']} / 완료 {stats['done']})"
        )

    if urgent:
        lines.append("")
        lines.append("🚨 마감 임박 업무")
        for t, days in sorted(urgent, key=lambda x: x[1]):
            label = "오늘 마감!" if days <= 0 else f"{days}일 남음"
            lines.append(f"  #{t['id']:03d} {t['content']} ({label})")

    await update.message.reply_text("\n".join(lines))


# ──────────────────────────────────────────
# /cancel 명령어
# ──────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel 업무번호 — 업무 취소 처리"""
    user_id = str(update.effective_user.id)
    data = _load_data()

    if user_id not in data["users"]:
        await update.message.reply_text("❌ 먼저 /register 로 역할을 등록해주세요.")
        return

    if not context.args:
        await update.message.reply_text("❌ 사용법: /cancel 업무번호\n예시: /cancel 1")
        return

    try:
        task_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 업무번호는 숫자로 입력해주세요.")
        return

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(f"❌ 업무 #{task_id:03d}을 찾을 수 없어요.")
        return

    # 완료된 업무는 취소 불가
    if task["status"] == "완료":
        await update.message.reply_text("❌ 이미 완료된 업무는 취소할 수 없어요.")
        return

    if task["status"] == "취소":
        await update.message.reply_text("❌ 이미 취소된 업무예요.")
        return

    # 권한 확인: 대표는 전체, 나머지는 본인 업무만
    user_role = data["users"][user_id]["role"]
    user_name = data["users"][user_id]["name"]
    if user_role != "대표" and task["assignee"] != user_name:
        await update.message.reply_text("❌ 본인에게 배정된 업무만 취소할 수 있어요.")
        return

    task["status"] = "취소"
    task["updates"].append({
        "date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "content": "업무 취소 처리",
        "by": user_name,
    })
    _save_data(data)

    await update.message.reply_text(
        f"🔴 업무 #{task_id:03d} 취소!\n\n{_format_task_card(task, data['users'])}"
    )


# ──────────────────────────────────────────
# 그룹챗 자동 감지
# ──────────────────────────────────────────

async def _track_group_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹 채팅방에서 메시지 수신 시 chat_id 저장"""
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        _save_group_chat_id(update.effective_chat.id)


# ──────────────────────────────────────────
# 스케줄 Job — 마감일 자동 알림 (매일 9시 KST)
# ──────────────────────────────────────────

async def _daily_deadline_reminder(context: ContextTypes.DEFAULT_TYPE):
    """매일 오전 9시(KST) 마감 알림"""
    group_ids = _get_group_chat_ids()
    if not group_ids:
        return

    data = _load_data()
    today = datetime.now(KST).date()

    overdue = []   # 마감 초과
    due_today = []  # 오늘 마감
    due_tomorrow = []  # 내일 마감

    for t in data["tasks"]:
        if t["status"] in ("완료", "취소"):
            continue
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d").date()
        except ValueError:
            continue

        diff = (dl - today).days
        if diff < 0:
            overdue.append(t)
        elif diff == 0:
            due_today.append(t)
        elif diff == 1:
            due_tomorrow.append(t)

    if not overdue and not due_today and not due_tomorrow:
        return

    lines = ["⏰ 마감일 알림\n"]

    if overdue:
        lines.append("❌ 마감 초과!")
        for t in overdue:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}) — 마감: {t['deadline']}")
        lines.append("")

    if due_today:
        lines.append("🚨 오늘 마감!")
        for t in due_today:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']})")
        lines.append("")

    if due_tomorrow:
        lines.append("⚠️ 내일 마감!")
        for t in due_tomorrow:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']})")

    text = "\n".join(lines)
    for cid in group_ids:
        try:
            await context.bot.send_message(chat_id=int(cid), text=text)
        except Exception as e:
            print(f"[telegram-bot] 마감 알림 전송 실패 (chat={cid}): {e}", flush=True)


# ──────────────────────────────────────────
# 스케줄 Job — 주간 보고서 (매주 월요일 9시 KST)
# ──────────────────────────────────────────

async def _generate_weekly_summary(tasks: list) -> str:
    """Claude API로 주간 업무 요약 생성"""
    if not ANTHROPIC_API_KEY:
        return ""
    try:
        # 요약에 필요한 핵심 정보만 추출
        summary_data = []
        for t in tasks:
            summary_data.append({
                "id": t["id"],
                "담당자": t["assignee"],
                "내용": t["content"],
                "마감": t["deadline"],
                "상태": t["status"],
                "진행률": t.get("progress", 0),
            })
        task_info = json.dumps(summary_data, ensure_ascii=False)

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=1000,
                system=(
                    "업무 관리 데이터를 받아서 한국어로 간결한 주간 요약을 작성하세요. "
                    "핵심 성과, 지연 사항, 주요 포인트를 3~5문장으로 정리하세요. "
                    "추가 설명이나 인사말 없이 요약만 출력하세요."
                ),
                messages=[{"role": "user", "content": f"이번 주 업무 데이터:\n{task_info}"}],
            ),
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[telegram-bot] 주간 요약 생성 실패: {e}", flush=True)
        return ""


async def _weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    """매주 월요일 오전 9시(KST) 주간 보고서 전송"""
    group_ids = _get_group_chat_ids()
    if not group_ids:
        return

    data = _load_data()
    tasks = data["tasks"]
    if not tasks:
        return

    # 상태별 분류
    active_tasks = [t for t in tasks if t["status"] not in ("완료", "취소")]
    completed = [t for t in tasks if t["status"] == "완료"]
    today = datetime.now(KST).date()
    overdue = []
    in_progress = []
    for t in active_tasks:
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d").date()
            if dl < today:
                overdue.append(t)
            else:
                in_progress.append(t)
        except ValueError:
            in_progress.append(t)

    lines = [
        "📊 주간 업무 보고서",
        f"날짜: {today.strftime('%Y.%m.%d')}\n",
        f"✅ 완료: {len(completed)}건",
        f"🟡 진행중: {len(in_progress)}건",
        f"❌ 지연: {len(overdue)}건",
        "",
    ]

    if overdue:
        lines.append("🚨 지연 업무")
        for t in overdue:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}) — 마감: {t['deadline']}")
        lines.append("")

    if in_progress:
        lines.append("🟡 진행중 업무")
        for t in in_progress:
            p = f" {t['progress']}%" if t.get("progress") else ""
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}){p}")
        lines.append("")

    # Claude AI 요약 추가
    ai_summary = await _generate_weekly_summary(tasks)
    if ai_summary:
        lines.append("💡 AI 요약")
        lines.append(ai_summary)

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (일부 생략)"

    for cid in group_ids:
        try:
            await context.bot.send_message(chat_id=int(cid), text=text)
        except Exception as e:
            print(f"[telegram-bot] 주간 보고서 전송 실패 (chat={cid}): {e}", flush=True)


# ──────────────────────────────────────────
# 봇 생성 및 실행
# ──────────────────────────────────────────

_bot_app: Application | None = None


async def start_telegram_bot():
    """텔레그램 봇 시작 — FastAPI startup 시 호출"""
    global _bot_app

    if not TELEGRAM_BOT_TOKEN:
        print("[telegram-bot] TELEGRAM_BOT_TOKEN 미설정 — 봇 비활성화", flush=True)
        return

    _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 명령어 핸들러 등록
    _bot_app.add_handler(CommandHandler("start", cmd_start))
    _bot_app.add_handler(CommandHandler("register", cmd_register))
    _bot_app.add_handler(CommandHandler("task", cmd_task))
    _bot_app.add_handler(CommandHandler("update", cmd_update))
    _bot_app.add_handler(CommandHandler("list", cmd_list))
    _bot_app.add_handler(CommandHandler("mylist", cmd_mylist))
    _bot_app.add_handler(CommandHandler("done", cmd_done))
    _bot_app.add_handler(CommandHandler("report", cmd_report))
    _bot_app.add_handler(CommandHandler("cancel", cmd_cancel))

    # 그룹챗 자동 감지 (group=-1: 다른 핸들러보다 먼저 실행)
    _bot_app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, _track_group_chat),
        group=-1,
    )

    # 텔레그램 봇 메뉴에 명령어 표시
    await _bot_app.bot.set_my_commands([
        BotCommand("start", "봇 소개"),
        BotCommand("register", "역할 등록"),
        BotCommand("task", "업무 등록"),
        BotCommand("update", "진행상황 업데이트"),
        BotCommand("list", "전체 업무 현황"),
        BotCommand("mylist", "내 업무 보기"),
        BotCommand("done", "업무 완료"),
        BotCommand("cancel", "업무 취소"),
        BotCommand("report", "전체 보고서 (대표 전용)"),
    ])

    # polling 시작 (비동기, non-blocking)
    await _bot_app.initialize()
    await _bot_app.start()
    await _bot_app.updater.start_polling(drop_pending_updates=True)

    # JobQueue 스케줄 등록 — 마감 알림 + 주간 보고서
    job_queue = _bot_app.job_queue
    if job_queue:
        # 매일 오전 9시(KST) 마감일 알림
        job_queue.run_daily(
            _daily_deadline_reminder,
            time=dt_time(hour=9, minute=0, tzinfo=KST),
            name="daily_deadline_reminder",
        )
        # 매주 월요일 오전 9시(KST) 주간 보고서
        job_queue.run_daily(
            _weekly_report_job,
            time=dt_time(hour=9, minute=0, tzinfo=KST),
            days=(0,),  # 0=월요일
            name="weekly_report",
        )
        print("[telegram-bot] 스케줄 등록: 매일 9시 마감알림 + 매주 월 9시 주간보고", flush=True)
    else:
        print("[telegram-bot] JobQueue 미사용 (APScheduler 미설치)", flush=True)

    print("[telegram-bot] 봇 시작됨 ✅", flush=True)


async def stop_telegram_bot():
    """텔레그램 봇 종료 — FastAPI shutdown 시 호출"""
    global _bot_app
    if _bot_app:
        await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()
        _bot_app = None
        print("[telegram-bot] 봇 종료됨", flush=True)
