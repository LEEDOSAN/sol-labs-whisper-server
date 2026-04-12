"""
텔레그램 업무관리 봇 — 인라인 키보드 기반
FastAPI와 같은 프로세스에서 실행 / SOL LABS AI 내부 업무 관리용
"""

import os
import json
import re
import asyncio
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
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


def _is_admin(user_id) -> bool:
    """TELEGRAM_ADMIN_ID 환경변수와 일치하는지 확인"""
    return bool(TELEGRAM_ADMIN_ID) and str(user_id) == str(TELEGRAM_ADMIN_ID)


def _get_user_role(user_id: str, data: dict) -> str | None:
    """유저 역할 반환 — 대표는 TELEGRAM_ADMIN_ID로 자동 판별"""
    if _is_admin(user_id):
        return "대표"
    user = data["users"].get(user_id)
    return user["role"] if user else None


def _ensure_admin_in_data(user, data: dict) -> dict:
    """대표를 users에 자동 등록 (TELEGRAM_ADMIN_ID 기반)"""
    uid = str(user.id)
    name = user.full_name or user.username or "대표"
    username = user.username or ""
    if uid not in data["users"] or data["users"][uid].get("role") != "대표":
        data["users"][uid] = {"name": name, "role": "대표", "username": username}
        _save_data(data)
    return data


def _track_user(user):
    """봇과 상호작용한 유저 정보 저장 (멤버 관리용)"""
    data = _load_data()
    if "known_users" not in data:
        data["known_users"] = {}
    uid = str(user.id)
    name = user.full_name or user.username or "Unknown"
    username = user.username or ""
    existing = data["known_users"].get(uid)
    if not existing or existing.get("name") != name:
        data["known_users"][uid] = {"name": name, "username": username}
        _save_data(data)


# ──────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────

def _progress_bar(percent: int) -> str:
    """진행률을 시각적 진행바로 변환"""
    filled = min(percent // 20, 5)
    return "🟩" * filled + "⬜" * (5 - filled)


def _needs_translation(text: str) -> bool:
    """한국어가 아닌 텍스트인지 판별 (러시아어/우즈벡어/영어)"""
    if re.search(r'[\u0400-\u04FF]', text):
        return True
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


def _format_task_card(task: dict, users: dict) -> str:
    """업무카드 형식으로 출력"""
    status_emoji = {"대기": "⚪", "진행중": "🟡", "완료": "🟢", "취소": "🔴"}
    emoji = status_emoji.get(task["status"], "⚪")

    assignee_role = ""
    for uinfo in users.values():
        if uinfo["name"] == task.get("assignee"):
            assignee_role = f" ({uinfo['role']})"
            break

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
# 키보드 빌더
# ──────────────────────────────────────────

def _main_menu_kb(user_id: str = None):
    """역할별 메인 메뉴 인라인 키보드"""
    is_admin = _is_admin(user_id) if user_id else False
    buttons = [
        [InlineKeyboardButton("📋 업무 등록", callback_data="task"),
         InlineKeyboardButton("📊 전체 현황", callback_data="list")],
        [InlineKeyboardButton("✅ 완료 처리", callback_data="done"),
         InlineKeyboardButton("❌ 업무 취소", callback_data="cancel_menu")],
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("👤 내 업무", callback_data="mylist"),
            InlineKeyboardButton("📈 보고서", callback_data="report"),
        ])
        buttons.append([InlineKeyboardButton("👥 멤버 관리", callback_data="members")])
    else:
        buttons.append([InlineKeyboardButton("👤 내 업무", callback_data="mylist")])
    return InlineKeyboardMarkup(buttons)


def _back_kb():
    """메인메뉴 버튼만"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")]
    ])


def _back_refresh_kb():
    """새로고침 + 메인메뉴"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 새로고침", callback_data="list"),
         InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")]
    ])


# ──────────────────────────────────────────
# /start, /menu — 메인 메뉴
# ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start 또는 /menu → 메인 메뉴 표시"""
    context.user_data.clear()
    user_id = str(update.effective_user.id)
    data = _load_data()
    _track_user(update.effective_user)

    # 대표 자동 등록
    if _is_admin(user_id):
        data = _ensure_admin_in_data(update.effective_user, data)

    role = _get_user_role(user_id, data)
    if not role:
        await update.message.reply_text(
            "👋 SOL LABS 업무관리 봇입니다!\n\n"
            "아직 역할이 없습니다.\n대표에게 역할 부여를 요청해주세요.",
            reply_markup=_back_kb(),
        )
        return

    name = data["users"][user_id]["name"]
    await update.message.reply_text(
        f"👋 {name}님 ({role})\nSOL LABS 업무관리 봇입니다!",
        reply_markup=_main_menu_kb(user_id),
    )


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """메인 메뉴 콜백 (버튼으로 돌아가기)"""
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    user_id = str(query.from_user.id)
    data = _load_data()

    if _is_admin(user_id):
        data = _ensure_admin_in_data(query.from_user, data)

    role = _get_user_role(user_id, data)
    if not role:
        await query.edit_message_text(
            "아직 역할이 없습니다.\n대표에게 역할 부여를 요청해주세요.",
            reply_markup=_back_kb(),
        )
        return

    name = data["users"][user_id]["name"]
    await query.edit_message_text(
        f"👋 {name}님 ({role})\nSOL LABS 업무관리 봇입니다!",
        reply_markup=_main_menu_kb(user_id),
    )


# ──────────────────────────────────────────
# 👥 멤버 관리 (대표 전용)
# ──────────────────────────────────────────

async def cb_members_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """멤버 관리 — 역할 없는 유저 목록 표시"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    if not _is_admin(user_id):
        await query.edit_message_text("❌ 멤버 관리는 대표만 가능합니다.", reply_markup=_back_kb())
        return

    data = _load_data()
    known = data.get("known_users", {})
    registered_ids = set(data["users"].keys())

    # 역할 없는 유저 + 이미 등록된 유저 분리
    unassigned = {uid: info for uid, info in known.items() if uid not in registered_ids}
    assigned = [
        (uid, data["users"][uid]) for uid in data["users"]
        if uid != user_id  # 대표 본인 제외
    ]

    lines = ["👥 멤버 관리\n"]

    if assigned:
        lines.append("── 등록된 멤버 ──")
        for uid, uinfo in assigned:
            lines.append(f"  {uinfo['name']} — {uinfo['role']}")
        lines.append("")

    buttons = []
    if unassigned:
        lines.append("── 역할 부여 대기 ──")
        for uid, info in unassigned.items():
            lines.append(f"  {info['name']}")
            buttons.append([InlineKeyboardButton(
                f"🏷️ {info['name']} 역할 부여",
                callback_data=f"ma:{uid}",
            )])
        lines.append("")
    else:
        lines.append("새 멤버가 그룹에서 메시지를 보내면\n여기에 표시됩니다.")

    buttons.append([InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")])

    await query.edit_message_text(
        "\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons)
    )


async def cb_member_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """멤버 선택 → 역할 선택 버튼 표시"""
    query = update.callback_query
    await query.answer()

    if not _is_admin(str(query.from_user.id)):
        await query.edit_message_text("❌ 권한이 없습니다.", reply_markup=_back_kb())
        return

    target_uid = query.data.split(":")[1]
    data = _load_data()
    known = data.get("known_users", {})
    target_info = known.get(target_uid)

    if not target_info:
        await query.edit_message_text("❌ 멤버를 찾을 수 없어요.", reply_markup=_back_kb())
        return

    name = target_info["name"]
    buttons = [
        [InlineKeyboardButton("개발자", callback_data=f"mr:{target_uid}:개발자"),
         InlineKeyboardButton("마케터", callback_data=f"mr:{target_uid}:마케터")],
        [InlineKeyboardButton("직원", callback_data=f"mr:{target_uid}:직원")],
        [InlineKeyboardButton("◀️ 멤버 목록", callback_data="members"),
         InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")],
    ]

    await query.edit_message_text(
        f"👥 멤버 관리\n\n{name}님에게 부여할 역할을 선택해주세요:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_assign_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """역할 부여 실행"""
    query = update.callback_query
    await query.answer()

    if not _is_admin(str(query.from_user.id)):
        await query.edit_message_text("❌ 권한이 없습니다.", reply_markup=_back_kb())
        return

    parts = query.data.split(":")
    target_uid = parts[1]
    role = parts[2]

    data = _load_data()
    known = data.get("known_users", {})
    target_info = known.get(target_uid)

    if not target_info:
        await query.edit_message_text("❌ 멤버를 찾을 수 없어요.", reply_markup=_back_kb())
        return

    name = target_info["name"]
    username = target_info.get("username", "")

    data["users"][target_uid] = {
        "name": name,
        "role": role,
        "username": username,
    }
    _save_data(data)

    admin_id = str(query.from_user.id)
    await query.edit_message_text(
        f"✅ @{name}님이 {role}(으)로 등록되었습니다.",
        reply_markup=_main_menu_kb(admin_id),
    )


async def cmd_resetroles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/resetroles — 대표만 가능, 모든 역할 초기화"""
    user_id = str(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ 이 명령어는 대표만 사용할 수 있어요.")
        return

    data = _load_data()
    # 대표 본인만 남기고 전부 제거
    admin_entry = data["users"].get(user_id)
    data["users"] = {}
    if admin_entry:
        data["users"][user_id] = admin_entry
    _save_data(data)

    await update.message.reply_text(
        "✅ 모든 멤버 역할이 초기화되었습니다.\n대표 역할만 유지됩니다.",
        reply_markup=_main_menu_kb(user_id),
    )


# ──────────────────────────────────────────
# 📋 업무 등록 플로우
# ──────────────────────────────────────────

async def cb_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """업무 등록 시작 → 담당자 선택"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = _load_data()
    if not _get_user_role(user_id, data):
        await query.edit_message_text("❌ 아직 역할이 없습니다.\n대표에게 역할 부여를 요청해주세요.", reply_markup=_back_kb())
        return

    # 등록된 멤버를 버튼으로 표시
    buttons = []
    row = []
    for uid, uinfo in data["users"].items():
        btn_text = f"{uinfo['name']}"
        row.append(InlineKeyboardButton(btn_text, callback_data=f"ta:{uid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("✏️ 직접 입력", callback_data="ta:custom")])
    buttons.append([InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")])

    await query.edit_message_text(
        "📋 업무 등록\n\n담당자를 선택해주세요:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_task_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """담당자 선택 → 업무 내용 입력 대기"""
    query = update.callback_query
    await query.answer()
    assignee_key = query.data.split(":")[1]

    if assignee_key == "custom":
        context.user_data["state"] = "awaiting_task_assignee"
        await query.edit_message_text(
            "📋 업무 등록\n\n담당자 이름을 입력해주세요:",
            reply_markup=_back_kb(),
        )
        return

    data = _load_data()
    if assignee_key in data["users"]:
        context.user_data["task_assignee"] = data["users"][assignee_key]["name"]
    else:
        context.user_data["task_assignee"] = assignee_key

    context.user_data["state"] = "awaiting_task_content"
    assignee = context.user_data["task_assignee"]
    await query.edit_message_text(
        f"📋 업무 등록\n담당자: {assignee}\n\n업무 내용을 입력해주세요:",
        reply_markup=_back_kb(),
    )


async def _process_task_assignee_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """직접 입력한 담당자 이름 → 업무 내용 입력 대기"""
    name = update.message.text.strip()
    context.user_data["task_assignee"] = name
    context.user_data["state"] = "awaiting_task_content"
    await update.message.reply_text(
        f"📋 업무 등록\n담당자: {name}\n\n업무 내용을 입력해주세요:",
        reply_markup=_back_kb(),
    )


async def _process_task_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """업무 내용 입력 → 마감일 선택"""
    content = update.message.text.strip()
    context.user_data["task_content"] = content
    context.user_data["state"] = None

    # 번역
    translated = None
    if _needs_translation(content):
        translated = await _translate_to_korean(content)
        if translated:
            context.user_data["task_translated"] = translated

    today = datetime.now(KST).date()
    buttons = [
        [
            InlineKeyboardButton(f"오늘 ({today.strftime('%m.%d')})", callback_data="td:0"),
            InlineKeyboardButton(f"내일 ({(today + timedelta(1)).strftime('%m.%d')})", callback_data="td:1"),
        ],
        [
            InlineKeyboardButton(f"3일 후 ({(today + timedelta(3)).strftime('%m.%d')})", callback_data="td:3"),
            InlineKeyboardButton(f"1주 후 ({(today + timedelta(7)).strftime('%m.%d')})", callback_data="td:7"),
        ],
        [InlineKeyboardButton("✏️ 직접 입력", callback_data="td:custom")],
        [InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")],
    ]

    assignee = context.user_data.get("task_assignee", "")
    display = translated or content
    text = f"📋 업무 등록\n담당자: {assignee}\n내용: {display}\n\n마감일을 선택해주세요:"
    if translated:
        text += f"\n\n[원본] {content}\n[번역] {translated}"

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def cb_task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """마감일 버튼 선택 → 업무 생성"""
    query = update.callback_query
    await query.answer()
    option = query.data.split(":")[1]

    if option == "custom":
        context.user_data["state"] = "awaiting_task_deadline"
        await query.edit_message_text(
            "마감일을 입력해주세요:\n형식: YYYY.MM.DD (예: 2026.04.18)",
            reply_markup=_back_kb(),
        )
        return

    days = int(option)
    deadline = (datetime.now(KST).date() + timedelta(days=days)).strftime("%Y.%m.%d")
    await _create_task_and_reply(query.from_user.id, context, deadline, query=query)


async def _process_task_deadline_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """직접 입력한 마감일 → 업무 생성"""
    deadline = update.message.text.strip()
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', deadline):
        await update.message.reply_text(
            "❌ 형식이 올바르지 않아요.\nYYYY.MM.DD (예: 2026.04.18)",
            reply_markup=_back_kb(),
        )
        return
    context.user_data["state"] = None
    await _create_task_and_reply(update.effective_user.id, context, deadline, message=update.message)


async def _create_task_and_reply(user_id, context, deadline, *, query=None, message=None):
    """업무 생성 공통 로직"""
    uid = str(user_id)
    data = _load_data()

    assignee = context.user_data.get("task_assignee", "미지정")
    content_original = context.user_data.get("task_content", "")
    translated = context.user_data.get("task_translated")
    content = translated or content_original
    creator_name = data["users"].get(uid, {}).get("name", "Unknown")

    task_id = data["next_id"]
    task = {
        "id": task_id,
        "assignee": assignee,
        "content": content,
        "content_original": content_original if translated else None,
        "deadline": deadline,
        "status": "대기",
        "progress": 0,
        "creator": creator_name,
        "creator_id": uid,
        "created_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "updates": [],
    }
    data["tasks"].append(task)
    data["next_id"] = task_id + 1
    _save_data(data)
    context.user_data.clear()

    reply = f"✅ 업무 등록 완료!\n\n{_format_task_card(task, data['users'])}"
    if translated:
        reply += f"\n\n[원본] {content_original}\n[번역] {translated}"

    if query:
        await query.edit_message_text(reply, reply_markup=_main_menu_kb(uid))
    elif message:
        await message.reply_text(reply, reply_markup=_main_menu_kb(uid))


# ──────────────────────────────────────────
# 📊 전체 현황
# ──────────────────────────────────────────

async def cb_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """전체 업무 목록 표시"""
    query = update.callback_query
    await query.answer()

    data = _load_data()
    tasks = data["tasks"]

    if not tasks:
        await query.edit_message_text("📋 등록된 업무가 없습니다.", reply_markup=_back_refresh_kb())
        return

    active = [t for t in tasks if t["status"] not in ("완료", "취소")]
    done = [t for t in tasks if t["status"] == "완료"]
    cancelled = [t for t in tasks if t["status"] == "취소"]

    lines = [f"📊 전체 업무 현황 (총 {len(tasks)}건)\n"]

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

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (더 많은 업무가 있어요)"

    await query.edit_message_text(text, reply_markup=_back_refresh_kb())


# ──────────────────────────────────────────
# ✅ 완료 처리
# ──────────────────────────────────────────

async def cb_done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """완료 처리 — 진행중 업무 버튼 표시"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = _load_data()
    user_role = _get_user_role(user_id, data)
    if not user_role:
        await query.edit_message_text("❌ 아직 역할이 없습니다.\n대표에게 역할 부여를 요청해주세요.", reply_markup=_back_kb())
        return

    user_name = data["users"].get(user_id, {}).get("name", "")
    active = [
        t for t in data["tasks"]
        if t["status"] not in ("완료", "취소")
        and (user_role == "대표" or t["assignee"] == user_name)
    ]

    if not active:
        await query.edit_message_text("📋 완료 처리할 업무가 없어요.", reply_markup=_back_kb())
        return

    buttons = []
    for t in active:
        buttons.append([InlineKeyboardButton(
            f"#{t['id']:03d} {t['content'][:25]}",
            callback_data=f"do:{t['id']}",
        )])
    buttons.append([InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")])

    await query.edit_message_text(
        "✅ 완료 처리\n\n완료할 업무를 선택해주세요:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """업무 완료 처리"""
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split(":")[1])

    user_id = str(query.from_user.id)
    data = _load_data()
    user_name = data["users"].get(user_id, {}).get("name", "")

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await query.edit_message_text("❌ 업무를 찾을 수 없어요.", reply_markup=_back_kb())
        return

    task["status"] = "완료"
    task["progress"] = 100
    task["updates"].append({
        "date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "content": "업무 완료 처리",
        "by": user_name,
    })
    _save_data(data)

    await query.edit_message_text(
        f"🟢 업무 #{task_id:03d} 완료!\n\n{_format_task_card(task, data['users'])}",
        reply_markup=_main_menu_kb(user_id),
    )


# ──────────────────────────────────────────
# ❌ 업무 취소
# ──────────────────────────────────────────

async def cb_cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """업무 취소 — 진행중 업무 버튼 표시"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = _load_data()
    user_role = _get_user_role(user_id, data)
    if not user_role:
        await query.edit_message_text("❌ 아직 역할이 없습니다.\n대표에게 역할 부여를 요청해주세요.", reply_markup=_back_kb())
        return

    user_name = data["users"].get(user_id, {}).get("name", "")
    active = [
        t for t in data["tasks"]
        if t["status"] not in ("완료", "취소")
        and (user_role == "대표" or t["assignee"] == user_name)
    ]

    if not active:
        await query.edit_message_text("📋 취소할 업무가 없어요.", reply_markup=_back_kb())
        return

    buttons = []
    for t in active:
        buttons.append([InlineKeyboardButton(
            f"#{t['id']:03d} {t['content'][:25]}",
            callback_data=f"ca:{t['id']}",
        )])
    buttons.append([InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")])

    await query.edit_message_text(
        "❌ 업무 취소\n\n취소할 업무를 선택해주세요:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """업무 취소 처리"""
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split(":")[1])

    user_id = str(query.from_user.id)
    data = _load_data()
    user_name = data["users"].get(user_id, {}).get("name", "")

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await query.edit_message_text("❌ 업무를 찾을 수 없어요.", reply_markup=_back_kb())
        return

    task["status"] = "취소"
    task["updates"].append({
        "date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "content": "업무 취소 처리",
        "by": user_name,
    })
    _save_data(data)

    await query.edit_message_text(
        f"🔴 업무 #{task_id:03d} 취소!\n\n{_format_task_card(task, data['users'])}",
        reply_markup=_main_menu_kb(user_id),
    )


# ──────────────────────────────────────────
# 👤 내 업무 + 진행률 업데이트
# ──────────────────────────────────────────

async def cb_mylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """내 업무 목록 + 진행률 업데이트 버튼"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = _load_data()
    if not _get_user_role(user_id, data):
        await query.edit_message_text("❌ 아직 역할이 없습니다.\n대표에게 역할 부여를 요청해주세요.", reply_markup=_back_kb())
        return

    user_name = data["users"][user_id]["name"]
    my_tasks = [t for t in data["tasks"] if t["assignee"] == user_name]

    if not my_tasks:
        await query.edit_message_text("📋 배정된 업무가 없습니다.", reply_markup=_back_kb())
        return

    lines = [f"👤 {user_name}님의 업무 ({len(my_tasks)}건)\n"]
    buttons = []
    for t in my_tasks:
        lines.append(_format_task_card(t, data["users"]))
        lines.append("")
        # 진행중/대기 업무에만 업데이트 버튼
        if t["status"] not in ("완료", "취소"):
            buttons.append([InlineKeyboardButton(
                f"📝 #{t['id']:03d} 진행률 업데이트",
                callback_data=f"up:{t['id']}",
            )])

    buttons.append([InlineKeyboardButton("🏠 메인메뉴", callback_data="menu")])

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (일부 생략)"

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def cb_update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """진행률 업데이트 시작 → % 입력 대기"""
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split(":")[1])

    context.user_data["state"] = "awaiting_progress"
    context.user_data["update_task_id"] = task_id

    await query.edit_message_text(
        f"📝 업무 #{task_id:03d} 진행률 업데이트\n\n"
        "진행 내용을 입력해주세요:\n"
        "예시: 사이드바 80% 완료\n"
        "예시: 70%",
        reply_markup=_back_kb(),
    )


async def _process_progress_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """진행률 텍스트 입력 처리"""
    task_id = context.user_data.get("update_task_id")
    if not task_id:
        context.user_data.clear()
        return

    user_id = str(update.effective_user.id)
    data = _load_data()
    user_name = data["users"].get(user_id, {}).get("name", "")
    update_content = update.message.text.strip()

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text("❌ 업무를 찾을 수 없어요.", reply_markup=_back_kb())
        context.user_data.clear()
        return

    # 번역
    translated = None
    if _needs_translation(update_content):
        translated = await _translate_to_korean(update_content)

    # 진행률 자동 감지
    progress_match = re.search(r'(\d+)\s*%', update_content)
    if progress_match:
        task["progress"] = int(progress_match.group(1))
        task["status"] = "진행중"
    elif task["status"] == "대기":
        task["status"] = "진행중"

    task["updates"].append({
        "date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "content": translated or update_content,
        "content_original": update_content if translated else None,
        "by": user_name,
    })
    _save_data(data)
    context.user_data.clear()

    reply = f"✅ 업무 #{task_id:03d} 업데이트 완료!\n\n{_format_task_card(task, data['users'])}"
    if translated and update_content != translated:
        reply += f"\n\n[원본] {update_content}\n[번역] {translated}"

    await update.message.reply_text(reply, reply_markup=_main_menu_kb(str(update.effective_user.id)))


# ──────────────────────────────────────────
# 📈 보고서 (대표 전용)
# ──────────────────────────────────────────

async def cb_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """전체 요약 보고서 — 대표만 가능"""
    query = update.callback_query
    await query.answer()

    user_id = str(query.from_user.id)
    data = _load_data()
    if not _is_admin(user_id):
        await query.edit_message_text("❌ 보고서는 대표만 확인할 수 있어요.", reply_markup=_back_kb())
        return

    tasks = data["tasks"]
    if not tasks:
        await query.edit_message_text("📊 등록된 업무가 없습니다.", reply_markup=_back_kb())
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

    # 마감 임박
    today = datetime.now(KST)
    urgent = []
    for t in tasks:
        if t["status"] in ("완료", "취소"):
            continue
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d")
            days_left = (dl - today).days
            if days_left <= 3:
                urgent.append((t, days_left))
        except ValueError:
            pass

    lines = [
        "📈 전체 업무 보고서",
        f"날짜: {today.strftime('%Y.%m.%d')}\n",
        f"📊 전체 현황: 총 {total}건",
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

    await query.edit_message_text("\n".join(lines), reply_markup=_back_kb())


# ──────────────────────────────────────────
# 텍스트 입력 라우터
# ──────────────────────────────────────────

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """상태에 따라 텍스트 입력을 적절한 처리기로 전달"""
    state = context.user_data.get("state")
    if not state:
        return

    if state == "awaiting_task_assignee":
        await _process_task_assignee_custom(update, context)
    elif state == "awaiting_task_content":
        await _process_task_content(update, context)
    elif state == "awaiting_task_deadline":
        await _process_task_deadline_custom(update, context)
    elif state == "awaiting_progress":
        await _process_progress_update(update, context)


# ──────────────────────────────────────────
# 그룹챗 자동 감지
# ──────────────────────────────────────────

async def _track_group_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """그룹 채팅방에서 메시지 수신 시 chat_id + 유저 정보 저장"""
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        _save_group_chat_id(update.effective_chat.id)
    if update.effective_user and not update.effective_user.is_bot:
        _track_user(update.effective_user)


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

    overdue = []
    due_today = []
    due_tomorrow = []

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

    # 명령어 핸들러
    _bot_app.add_handler(CommandHandler("start", cmd_start))
    _bot_app.add_handler(CommandHandler("menu", cmd_start))
    _bot_app.add_handler(CommandHandler("resetroles", cmd_resetroles))

    # 콜백 쿼리 핸들러 (인라인 키보드 버튼)
    _bot_app.add_handler(CallbackQueryHandler(cb_menu, pattern="^menu$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_members_start, pattern="^members$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_member_select, pattern=r"^ma:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_assign_role, pattern=r"^mr:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_start, pattern="^task$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_assignee, pattern=r"^ta:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_deadline, pattern=r"^td:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_list, pattern="^list$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_done_start, pattern="^done$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_done, pattern=r"^do:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_cancel_start, pattern="^cancel_menu$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_cancel, pattern=r"^ca:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_mylist, pattern="^mylist$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_update_start, pattern=r"^up:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_report, pattern="^report$"))

    # 텍스트 입력 핸들러 (상태 기반 라우팅)
    _bot_app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_text_input
    ))

    # 그룹챗 자동 감지 (group=-1: 다른 핸들러보다 먼저 실행)
    _bot_app.add_handler(
        MessageHandler(filters.ChatType.GROUPS, _track_group_chat),
        group=-1,
    )

    # 텔레그램 봇 메뉴에 명령어 표시
    await _bot_app.bot.set_my_commands([
        BotCommand("start", "메인 메뉴"),
        BotCommand("menu", "메인 메뉴"),
        BotCommand("resetroles", "역할 초기화 (대표 전용)"),
    ])

    # polling 시작
    await _bot_app.initialize()
    await _bot_app.start()
    await _bot_app.updater.start_polling(drop_pending_updates=True)

    # JobQueue 스케줄 등록
    job_queue = _bot_app.job_queue
    if job_queue:
        job_queue.run_daily(
            _daily_deadline_reminder,
            time=dt_time(hour=9, minute=0, tzinfo=KST),
            name="daily_deadline_reminder",
        )
        job_queue.run_daily(
            _weekly_report_job,
            time=dt_time(hour=9, minute=0, tzinfo=KST),
            days=(0,),
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
