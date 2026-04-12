"""
텔레그램 업무관리 봇 — 인라인 키보드 + 다국어 지원
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

# 파일 경로
TASKS_FILE = Path(__file__).parent / "tasks.json"
LANG_FILE = Path(__file__).parent / "users.json"

# KST 타임존
KST = ZoneInfo("Asia/Seoul")


# ──────────────────────────────────────────
# 다국어 번역 사전
# ──────────────────────────────────────────

_T = {
    "ko": {
        # 메인 메뉴 버튼
        "menu_task": "📋 업무 등록", "menu_status": "📊 전체 현황",
        "menu_done": "✅ 완료 처리", "menu_cancel": "❌ 업무 취소",
        "menu_my": "👤 내 업무", "menu_report": "📈 보고서",
        "menu_members": "👥 멤버 관리", "menu_lang": "🌐 언어",
        "menu_home": "🏠 메인메뉴", "menu_refresh": "🔄 새로고침",
        # 업무카드
        "card_assigned": "담당", "card_task": "내용", "card_due": "마감",
        "card_status": "상태", "card_by": "등록자", "card_progress": "진행",
        # 상태
        "st_pending": "⚪ 대기", "st_progress": "🟡 진행중",
        "st_done": "✅ 완료", "st_cancelled": "🔴 취소",
        # 메시지
        "welcome": "👋 SOL LABS 업무관리 봇입니다!",
        "no_role": "아직 역할이 없습니다.\nCEO에게 역할 부여를 요청해주세요.",
        "no_perm": "❌ 권한이 없습니다.",
        "members_only": "❌ 멤버 관리는 CEO만 가능합니다.",
        "report_only": "❌ 보고서는 CEO만 확인할 수 있어요.",
        "reset_only": "❌ 이 명령어는 CEO만 사용할 수 있어요.",
        "not_found": "❌ 업무를 찾을 수 없어요.",
        "no_tasks": "📋 등록된 업무가 없습니다.",
        "no_my": "📋 배정된 업무가 없습니다.",
        "no_done": "📋 완료 처리할 업무가 없어요.",
        "no_cancel": "📋 취소할 업무가 없어요.",
        # 업무 등록
        "task_title": "📋 업무 등록", "sel_assignee": "담당자를 선택해주세요:",
        "enter_assignee": "담당자 이름을 입력해주세요:",
        "enter_content": "업무 내용을 입력해주세요:",
        "sel_deadline": "마감일을 선택해주세요:",
        "enter_deadline": "마감일을 입력해주세요:\n형식: YYYY.MM.DD (예: 2026.04.18)",
        "bad_date": "❌ 형식이 올바르지 않아요.\nYYYY.MM.DD (예: 2026.04.18)",
        "custom": "✏️ 직접 입력",
        "task_ok": "✅ 업무 등록 완료!",
        "d_today": "오늘", "d_tomorrow": "내일", "d_3": "3일 후", "d_7": "1주 후",
        # 완료/취소
        "sel_done": "완료할 업무를 선택해주세요:",
        "sel_cancel": "취소할 업무를 선택해주세요:",
        "done_ok": "🟢 업무 #{id} 완료!", "cancel_ok": "🔴 업무 #{id} 취소!",
        # 내 업무
        "my_title": "👤 {name}님의 업무 ({count}건)",
        "upd_btn": "📝 진행률 업데이트",
        "enter_progress": "진행 내용을 입력해주세요:\n예시: 사이드바 80% 완료\n예시: 70%",
        "upd_ok": "✅ 업무 #{id} 업데이트 완료!",
        "original": "원본", "translated": "번역",
        # 멤버 관리
        "mem_title": "👥 멤버 관리",
        "mem_registered": "── 등록된 멤버 ──",
        "mem_unassigned": "── 역할 부여 대기 ──",
        "mem_assign": "🏷️ {name} 역할 부여",
        "mem_sel_role": "{name}님에게 부여할 역할을 선택해주세요:",
        "mem_ok": "✅ @{name}님이 {role}(으)로 등록되었습니다.",
        "mem_404": "❌ 멤버를 찾을 수 없어요.",
        "mem_hint": "새 멤버가 그룹에서 메시지를 보내면\n여기에 표시됩니다.",
        "mem_back": "◀️ 멤버 목록",
        "reset_ok": "✅ 모든 멤버 역할이 초기화되었습니다.\nCEO 역할만 유지됩니다.",
        # 보고서/현황
        "rpt_title": "📈 전체 업무 보고서",
        "all_title": "📊 전체 업무 현황 (총 {count}건)",
        "sec_active": "── 진행 중 ──",
        "sec_done": "── 완료 ({count}건) ──",
        "sec_cancel": "── 취소 ({count}건) ──",
        # 언어
        "lang_set": "✅ 언어가 한국어로 설정되었습니다",
        "sel_lang": "🌐 언어를 선택해주세요:",
    },
    "en": {
        "menu_task": "📋 Add Task", "menu_status": "📊 Status",
        "menu_done": "✅ Done", "menu_cancel": "❌ Cancel",
        "menu_my": "👤 My Tasks", "menu_report": "📈 Report",
        "menu_members": "👥 Members", "menu_lang": "🌐 Language",
        "menu_home": "🏠 Main Menu", "menu_refresh": "🔄 Refresh",
        "card_assigned": "Assigned", "card_task": "Task", "card_due": "Due",
        "card_status": "Status", "card_by": "By", "card_progress": "Progress",
        "st_pending": "⚪ Pending", "st_progress": "🟡 In Progress",
        "st_done": "✅ Done", "st_cancelled": "🔴 Cancelled",
        "welcome": "👋 SOL LABS Task Manager Bot!",
        "no_role": "You don't have a role yet.\nPlease ask the CEO to assign one.",
        "no_perm": "❌ No permission.",
        "members_only": "❌ Members management is CEO only.",
        "report_only": "❌ Report is available for CEO only.",
        "reset_only": "❌ This command is for CEO only.",
        "not_found": "❌ Task not found.",
        "no_tasks": "📋 No tasks registered.",
        "no_my": "📋 No tasks assigned to you.",
        "no_done": "📋 No tasks to complete.",
        "no_cancel": "📋 No tasks to cancel.",
        "task_title": "📋 Add Task", "sel_assignee": "Select assignee:",
        "enter_assignee": "Enter assignee name:",
        "enter_content": "Enter task description:",
        "sel_deadline": "Select deadline:",
        "enter_deadline": "Enter deadline:\nFormat: YYYY.MM.DD (e.g. 2026.04.18)",
        "bad_date": "❌ Invalid format.\nYYYY.MM.DD (e.g. 2026.04.18)",
        "custom": "✏️ Custom Input",
        "task_ok": "✅ Task created!",
        "d_today": "Today", "d_tomorrow": "Tomorrow", "d_3": "In 3 days", "d_7": "In 1 week",
        "sel_done": "Select task to complete:",
        "sel_cancel": "Select task to cancel:",
        "done_ok": "🟢 Task #{id} completed!", "cancel_ok": "🔴 Task #{id} cancelled!",
        "my_title": "👤 {name}'s Tasks ({count})",
        "upd_btn": "📝 Update Progress",
        "enter_progress": "Enter progress:\nExample: sidebar 80% done\nExample: 70%",
        "upd_ok": "✅ Task #{id} updated!",
        "original": "Original", "translated": "Translated",
        "mem_title": "👥 Member Management",
        "mem_registered": "── Registered ──",
        "mem_unassigned": "── Pending Assignment ──",
        "mem_assign": "🏷️ Assign {name}",
        "mem_sel_role": "Select a role for {name}:",
        "mem_ok": "✅ @{name} has been assigned as {role}.",
        "mem_404": "❌ Member not found.",
        "mem_hint": "New members will appear here\nwhen they message in the group.",
        "mem_back": "◀️ Back to Members",
        "reset_ok": "✅ All roles have been reset.\nOnly CEO role is preserved.",
        "rpt_title": "📈 Task Report",
        "all_title": "📊 All Tasks ({count} total)",
        "sec_active": "── Active ──",
        "sec_done": "── Done ({count}) ──",
        "sec_cancel": "── Cancelled ({count}) ──",
        "lang_set": "✅ Language set to English",
        "sel_lang": "🌐 Select your language:",
    },
    "ru": {
        "menu_task": "📋 Задача", "menu_status": "📊 Статус",
        "menu_done": "✅ Готово", "menu_cancel": "❌ Отмена",
        "menu_my": "👤 Мои задачи", "menu_report": "📈 Отчёт",
        "menu_members": "👥 Участники", "menu_lang": "🌐 Язык",
        "menu_home": "🏠 Главное меню", "menu_refresh": "🔄 Обновить",
        "card_assigned": "Исполнитель", "card_task": "Задача", "card_due": "Срок",
        "card_status": "Статус", "card_by": "От", "card_progress": "Прогресс",
        "st_pending": "⚪ Ожидание", "st_progress": "🟡 В работе",
        "st_done": "✅ Готово", "st_cancelled": "🔴 Отменено",
        "welcome": "👋 SOL LABS — бот управления задачами!",
        "no_role": "У вас ещё нет роли.\nПопросите CEO назначить вам роль.",
        "no_perm": "❌ Нет доступа.",
        "members_only": "❌ Управление участниками доступно только CEO.",
        "report_only": "❌ Отчёт доступен только CEO.",
        "reset_only": "❌ Эта команда доступна только CEO.",
        "not_found": "❌ Задача не найдена.",
        "no_tasks": "📋 Нет зарегистрированных задач.",
        "no_my": "📋 Нет назначенных задач.",
        "no_done": "📋 Нет задач для завершения.",
        "no_cancel": "📋 Нет задач для отмены.",
        "task_title": "📋 Новая задача", "sel_assignee": "Выберите исполнителя:",
        "enter_assignee": "Введите имя исполнителя:",
        "enter_content": "Введите описание задачи:",
        "sel_deadline": "Выберите срок:",
        "enter_deadline": "Введите дату:\nФормат: ГГГГ.ММ.ДД (напр. 2026.04.18)",
        "bad_date": "❌ Неверный формат.\nГГГГ.ММ.ДД (напр. 2026.04.18)",
        "custom": "✏️ Ввести вручную",
        "task_ok": "✅ Задача создана!",
        "d_today": "Сегодня", "d_tomorrow": "Завтра", "d_3": "Через 3 дня", "d_7": "Через неделю",
        "sel_done": "Выберите задачу для завершения:",
        "sel_cancel": "Выберите задачу для отмены:",
        "done_ok": "🟢 Задача #{id} завершена!", "cancel_ok": "🔴 Задача #{id} отменена!",
        "my_title": "👤 Задачи {name} ({count})",
        "upd_btn": "📝 Обновить прогресс",
        "enter_progress": "Введите обновление:\nПример: сайдбар 80% готов\nПример: 70%",
        "upd_ok": "✅ Задача #{id} обновлена!",
        "original": "Оригинал", "translated": "Перевод",
        "mem_title": "👥 Управление участниками",
        "mem_registered": "── Зарегистрированные ──",
        "mem_unassigned": "── Ожидают роль ──",
        "mem_assign": "🏷️ Назначить {name}",
        "mem_sel_role": "Выберите роль для {name}:",
        "mem_ok": "✅ @{name} назначен как {role}.",
        "mem_404": "❌ Участник не найден.",
        "mem_hint": "Новые участники появятся здесь,\nкогда напишут в группе.",
        "mem_back": "◀️ К участникам",
        "reset_ok": "✅ Все роли сброшены.\nСохранена только роль CEO.",
        "rpt_title": "📈 Отчёт по задачам",
        "all_title": "📊 Все задачи (всего {count})",
        "sec_active": "── Активные ──",
        "sec_done": "── Готово ({count}) ──",
        "sec_cancel": "── Отменено ({count}) ──",
        "lang_set": "✅ Язык установлен на русский",
        "sel_lang": "🌐 Выберите язык:",
    },
    "uz": {
        "menu_task": "📋 Vazifa", "menu_status": "📊 Holat",
        "menu_done": "✅ Bajarildi", "menu_cancel": "❌ Bekor",
        "menu_my": "👤 Mening", "menu_report": "📈 Hisobot",
        "menu_members": "👥 A'zolar", "menu_lang": "🌐 Til",
        "menu_home": "🏠 Asosiy menyu", "menu_refresh": "🔄 Yangilash",
        "card_assigned": "Mas'ul", "card_task": "Vazifa", "card_due": "Muddat",
        "card_status": "Holat", "card_by": "Kim", "card_progress": "Jarayon",
        "st_pending": "⚪ Kutilmoqda", "st_progress": "🟡 Jarayonda",
        "st_done": "✅ Bajarildi", "st_cancelled": "🔴 Bekor",
        "welcome": "👋 SOL LABS vazifa boshqaruv boti!",
        "no_role": "Sizga rol tayinlanmagan.\nCEOdan rol so'rang.",
        "no_perm": "❌ Ruxsat yo'q.",
        "members_only": "❌ A'zolarni boshqarish faqat CEO uchun.",
        "report_only": "❌ Hisobot faqat CEO uchun.",
        "reset_only": "❌ Bu buyruq faqat CEO uchun.",
        "not_found": "❌ Vazifa topilmadi.",
        "no_tasks": "📋 Vazifalar yo'q.",
        "no_my": "📋 Sizga tayinlangan vazifalar yo'q.",
        "no_done": "📋 Bajarilishi kerak bo'lgan vazifalar yo'q.",
        "no_cancel": "📋 Bekor qilinadigan vazifalar yo'q.",
        "task_title": "📋 Yangi vazifa", "sel_assignee": "Mas'ulni tanlang:",
        "enter_assignee": "Mas'ul ismini kiriting:",
        "enter_content": "Vazifa tavsifini kiriting:",
        "sel_deadline": "Muddatni tanlang:",
        "enter_deadline": "Sanani kiriting:\nFormat: YYYY.MM.DD (masalan: 2026.04.18)",
        "bad_date": "❌ Noto'g'ri format.\nYYYY.MM.DD (masalan: 2026.04.18)",
        "custom": "✏️ Qo'lda kiritish",
        "task_ok": "✅ Vazifa yaratildi!",
        "d_today": "Bugun", "d_tomorrow": "Ertaga", "d_3": "3 kundan keyin", "d_7": "1 haftadan keyin",
        "sel_done": "Bajariladigan vazifani tanlang:",
        "sel_cancel": "Bekor qilinadigan vazifani tanlang:",
        "done_ok": "🟢 Vazifa #{id} bajarildi!", "cancel_ok": "🔴 Vazifa #{id} bekor qilindi!",
        "my_title": "👤 {name} vazifalari ({count})",
        "upd_btn": "📝 Jarayonni yangilash",
        "enter_progress": "Yangilanishni kiriting:\nMisol: sidebar 80% tayyor\nMisol: 70%",
        "upd_ok": "✅ Vazifa #{id} yangilandi!",
        "original": "Asl nusxa", "translated": "Tarjima",
        "mem_title": "👥 A'zolarni boshqarish",
        "mem_registered": "── Ro'yxatdagilar ──",
        "mem_unassigned": "── Rol kutilmoqda ──",
        "mem_assign": "🏷️ {name}ga rol berish",
        "mem_sel_role": "{name} uchun rol tanlang:",
        "mem_ok": "✅ @{name} {role} sifatida tayinlandi.",
        "mem_404": "❌ A'zo topilmadi.",
        "mem_hint": "Yangi a'zolar guruhda yozganda\nbu yerda ko'rinadi.",
        "mem_back": "◀️ A'zolarga qaytish",
        "reset_ok": "✅ Barcha rollar tiklandi.\nFaqat CEO roli saqlandi.",
        "rpt_title": "📈 Vazifa hisoboti",
        "all_title": "📊 Barcha vazifalar (jami {count})",
        "sec_active": "── Faol ──",
        "sec_done": "── Bajarildi ({count}) ──",
        "sec_cancel": "── Bekor ({count}) ──",
        "lang_set": "✅ Til o'zbek tiliga o'rnatildi",
        "sel_lang": "🌐 Tilni tanlang:",
    },
}

# 내부 상태값 → 번역 키 매핑
_STATUS_KEY = {"대기": "st_pending", "진행중": "st_progress", "완료": "st_done", "취소": "st_cancelled"}


def _t(key: str, lang: str = "ko") -> str:
    """번역 키 → 해당 언어 텍스트 (fallback: 한국어)"""
    return _T.get(lang, _T["ko"]).get(key, _T["ko"].get(key, key))


# ──────────────────────────────────────────
# 데이터 저장/로드
# ──────────────────────────────────────────

def _load_data() -> dict:
    if TASKS_FILE.exists():
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"next_id": 1, "users": {}, "tasks": []}


def _save_data(data: dict):
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_lang() -> dict:
    if LANG_FILE.exists():
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_lang(prefs: dict):
    with open(LANG_FILE, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)


def _get_user_lang(user_id) -> str:
    prefs = _load_lang()
    return prefs.get(str(user_id), "ko")


def _set_user_lang(user_id, lang: str):
    prefs = _load_lang()
    prefs[str(user_id)] = lang
    _save_lang(prefs)


def _save_group_chat_id(chat_id: int):
    data = _load_data()
    if "group_chat_ids" not in data:
        data["group_chat_ids"] = []
    cid = str(chat_id)
    if cid not in data["group_chat_ids"]:
        data["group_chat_ids"].append(cid)
        _save_data(data)
        print(f"[telegram-bot] 그룹챗 등록: {chat_id}", flush=True)


def _get_group_chat_ids() -> list[str]:
    data = _load_data()
    return data.get("group_chat_ids", [])


# ──────────────────────────────────────────
# 권한/유저 헬퍼
# ──────────────────────────────────────────

def _is_admin(user_id) -> bool:
    return bool(TELEGRAM_ADMIN_ID) and str(user_id) == str(TELEGRAM_ADMIN_ID)


def _get_user_role(user_id: str, data: dict) -> str | None:
    if _is_admin(user_id):
        return "CEO"
    user = data["users"].get(user_id)
    return user["role"] if user else None


def _ensure_admin_in_data(user, data: dict) -> dict:
    uid = str(user.id)
    name = user.full_name or user.username or "CEO"
    username = user.username or ""
    if uid not in data["users"] or data["users"][uid].get("role") != "CEO":
        data["users"][uid] = {"name": name, "role": "CEO", "username": username}
        _save_data(data)
    return data


def _track_user(user):
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
    filled = min(percent // 20, 5)
    return "🟩" * filled + "⬜" * (5 - filled)


def _needs_translation(text: str) -> bool:
    if re.search(r'[\u0400-\u04FF]', text):
        return True
    korean = len(re.findall(r'[\uAC00-\uD7A3]', text))
    latin = len(re.findall(r'[a-zA-Z]', text))
    return latin > 3 and latin > korean


async def _translate_to_korean(text: str) -> str | None:
    if not ANTHROPIC_API_KEY:
        return None
    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model="claude-sonnet-4-5", max_tokens=500,
                system="당신은 번역 전문가입니다. 주어진 텍스트를 한국어로 번역하세요. 번역된 텍스트만 출력하세요.",
                messages=[{"role": "user", "content": text}],
            ),
        )
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[telegram-bot] 번역 실패: {e}", flush=True)
        return None


def _format_task_card(task: dict, users: dict, lang: str = "ko") -> str:
    status_key = _STATUS_KEY.get(task["status"], "st_pending")
    status_text = _t(status_key, lang)

    assignee_role = ""
    for uinfo in users.values():
        if uinfo["name"] == task.get("assignee"):
            assignee_role = f" ({uinfo['role']})"
            break

    progress_line = ""
    if task.get("progress") and task["status"] not in ("완료", "취소"):
        progress_line = f"\n{_t('card_progress', lang)}: {_progress_bar(task['progress'])} {task['progress']}%"

    return (
        f"📋 #{task['id']:03d}\n"
        f"{_t('card_assigned', lang)}: @{task['assignee']}{assignee_role}\n"
        f"{_t('card_task', lang)}: {task['content']}\n"
        f"{_t('card_due', lang)}: {task['deadline']}\n"
        f"{_t('card_status', lang)}: {status_text}{progress_line}\n"
        f"{_t('card_by', lang)}: @{task['creator']}"
    )


# ──────────────────────────────────────────
# 키보드 빌더
# ──────────────────────────────────────────

def _main_menu_kb(user_id: str = None, lang: str = "ko"):
    is_admin = _is_admin(user_id) if user_id else False
    L = lang
    buttons = [
        [InlineKeyboardButton(_t("menu_task", L), callback_data="task"),
         InlineKeyboardButton(_t("menu_status", L), callback_data="list")],
        [InlineKeyboardButton(_t("menu_done", L), callback_data="done"),
         InlineKeyboardButton(_t("menu_cancel", L), callback_data="cancel_menu")],
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton(_t("menu_my", L), callback_data="mylist"),
            InlineKeyboardButton(_t("menu_report", L), callback_data="report"),
        ])
        buttons.append([
            InlineKeyboardButton(_t("menu_members", L), callback_data="members"),
            InlineKeyboardButton(_t("menu_lang", L), callback_data="lang"),
        ])
    else:
        buttons.append([
            InlineKeyboardButton(_t("menu_my", L), callback_data="mylist"),
            InlineKeyboardButton(_t("menu_lang", L), callback_data="lang"),
        ])
    return InlineKeyboardMarkup(buttons)


def _back_kb(lang: str = "ko"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")]
    ])


def _back_refresh_kb(lang: str = "ko"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("menu_refresh", lang), callback_data="list"),
         InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")]
    ])


# ──────────────────────────────────────────
# /start, /menu — 메인 메뉴
# ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    _track_user(update.effective_user)

    if _is_admin(user_id):
        data = _ensure_admin_in_data(update.effective_user, data)

    role = _get_user_role(user_id, data)
    if not role:
        await update.message.reply_text(
            f"{_t('welcome', lang)}\n\n{_t('no_role', lang)}", reply_markup=_back_kb(lang))
        return

    name = data["users"][user_id]["name"]
    await update.message.reply_text(
        f"{_t('welcome', lang)}\n{name} ({role})",
        reply_markup=_main_menu_kb(user_id, lang))


async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()

    if _is_admin(user_id):
        data = _ensure_admin_in_data(query.from_user, data)

    role = _get_user_role(user_id, data)
    if not role:
        await query.edit_message_text(_t("no_role", lang), reply_markup=_back_kb(lang))
        return

    name = data["users"][user_id]["name"]
    await query.edit_message_text(
        f"{_t('welcome', lang)}\n{name} ({role})",
        reply_markup=_main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 🌐 언어 선택
# ──────────────────────────────────────────

async def cb_lang_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = _get_user_lang(str(query.from_user.id))
    buttons = [
        [InlineKeyboardButton("🇰🇷 한국어", callback_data="setlang:ko")],
        [InlineKeyboardButton("🇺🇸 English", callback_data="setlang:en")],
        [InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang:ru")],
        [InlineKeyboardButton("🇺🇿 O'zbek", callback_data="setlang:uz")],
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")],
    ]
    await query.edit_message_text(
        _t("sel_lang", lang), reply_markup=InlineKeyboardMarkup(buttons))


async def cb_set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    new_lang = query.data.split(":")[1]
    _set_user_lang(user_id, new_lang)
    await query.edit_message_text(
        _t("lang_set", new_lang), reply_markup=_main_menu_kb(user_id, new_lang))


# ──────────────────────────────────────────
# 👥 멤버 관리 (CEO 전용)
# ──────────────────────────────────────────

async def cb_members_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)

    if not _is_admin(user_id):
        await query.edit_message_text(_t("members_only", lang), reply_markup=_back_kb(lang))
        return

    data = _load_data()
    known = data.get("known_users", {})
    registered_ids = set(data["users"].keys())
    unassigned = {uid: info for uid, info in known.items() if uid not in registered_ids}
    assigned = [(uid, data["users"][uid]) for uid in data["users"] if uid != user_id]

    lines = [f"{_t('mem_title', lang)}\n"]
    if assigned:
        lines.append(_t("mem_registered", lang))
        for _, uinfo in assigned:
            lines.append(f"  {uinfo['name']} — {uinfo['role']}")
        lines.append("")

    buttons = []
    if unassigned:
        lines.append(_t("mem_unassigned", lang))
        for uid, info in unassigned.items():
            lines.append(f"  {info['name']}")
            buttons.append([InlineKeyboardButton(
                _t("mem_assign", lang).format(name=info["name"]),
                callback_data=f"ma:{uid}")])
        lines.append("")
    else:
        lines.append(_t("mem_hint", lang))

    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await query.edit_message_text("\n".join(lines), reply_markup=InlineKeyboardMarkup(buttons))


async def cb_member_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)

    if not _is_admin(user_id):
        await query.edit_message_text(_t("no_perm", lang), reply_markup=_back_kb(lang))
        return

    target_uid = query.data.split(":")[1]
    data = _load_data()
    target_info = data.get("known_users", {}).get(target_uid)
    if not target_info:
        await query.edit_message_text(_t("mem_404", lang), reply_markup=_back_kb(lang))
        return

    name = target_info["name"]
    buttons = [
        [InlineKeyboardButton("CEO", callback_data=f"mr:{target_uid}:CEO"),
         InlineKeyboardButton("Developer", callback_data=f"mr:{target_uid}:Developer")],
        [InlineKeyboardButton("CMO", callback_data=f"mr:{target_uid}:CMO"),
         InlineKeyboardButton("🐝 여왕벌", callback_data=f"mr:{target_uid}:🐝 여왕벌")],
        [InlineKeyboardButton("Member", callback_data=f"mr:{target_uid}:Member")],
        [InlineKeyboardButton(_t("mem_back", lang), callback_data="members"),
         InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")],
    ]
    await query.edit_message_text(
        f"{_t('mem_title', lang)}\n\n{_t('mem_sel_role', lang).format(name=name)}",
        reply_markup=InlineKeyboardMarkup(buttons))


async def cb_assign_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = str(query.from_user.id)
    lang = _get_user_lang(admin_id)

    if not _is_admin(admin_id):
        await query.edit_message_text(_t("no_perm", lang), reply_markup=_back_kb(lang))
        return

    parts = query.data.split(":")
    target_uid, role = parts[1], parts[2]
    data = _load_data()
    target_info = data.get("known_users", {}).get(target_uid)
    if not target_info:
        await query.edit_message_text(_t("mem_404", lang), reply_markup=_back_kb(lang))
        return

    name = target_info["name"]
    data["users"][target_uid] = {"name": name, "role": role, "username": target_info.get("username", "")}
    _save_data(data)
    await query.edit_message_text(
        _t("mem_ok", lang).format(name=name, role=role),
        reply_markup=_main_menu_kb(admin_id, lang))


async def cmd_resetroles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await update.message.reply_text(_t("reset_only", lang))
        return
    data = _load_data()
    admin_entry = data["users"].get(user_id)
    data["users"] = {}
    if admin_entry:
        data["users"][user_id] = admin_entry
    _save_data(data)
    await update.message.reply_text(_t("reset_ok", lang), reply_markup=_main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 📋 업무 등록 플로우
# ──────────────────────────────────────────

async def cb_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    if not _get_user_role(user_id, data):
        await query.edit_message_text(_t("no_role", lang), reply_markup=_back_kb(lang))
        return

    buttons = []
    row = []
    for uid, uinfo in data["users"].items():
        row.append(InlineKeyboardButton(uinfo["name"], callback_data=f"ta:{uid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(_t("custom", lang), callback_data="ta:custom")])
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await query.edit_message_text(
        f"{_t('task_title', lang)}\n\n{_t('sel_assignee', lang)}",
        reply_markup=InlineKeyboardMarkup(buttons))


async def cb_task_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    assignee_key = query.data.split(":")[1]

    if assignee_key == "custom":
        context.user_data["state"] = "awaiting_task_assignee"
        await query.edit_message_text(
            f"{_t('task_title', lang)}\n\n{_t('enter_assignee', lang)}",
            reply_markup=_back_kb(lang))
        return

    data = _load_data()
    context.user_data["task_assignee"] = data["users"].get(assignee_key, {}).get("name", assignee_key)
    context.user_data["state"] = "awaiting_task_content"
    a = context.user_data["task_assignee"]
    await query.edit_message_text(
        f"{_t('task_title', lang)}\n{_t('card_assigned', lang)}: {a}\n\n{_t('enter_content', lang)}",
        reply_markup=_back_kb(lang))


async def _process_task_assignee_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _get_user_lang(str(update.effective_user.id))
    name = update.message.text.strip()
    context.user_data["task_assignee"] = name
    context.user_data["state"] = "awaiting_task_content"
    await update.message.reply_text(
        f"{_t('task_title', lang)}\n{_t('card_assigned', lang)}: {name}\n\n{_t('enter_content', lang)}",
        reply_markup=_back_kb(lang))


async def _process_task_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    content = update.message.text.strip()
    context.user_data["task_content"] = content
    context.user_data["state"] = None

    translated = None
    if _needs_translation(content):
        translated = await _translate_to_korean(content)
        if translated:
            context.user_data["task_translated"] = translated

    today = datetime.now(KST).date()
    buttons = [
        [InlineKeyboardButton(f"{_t('d_today', lang)} ({today.strftime('%m.%d')})", callback_data="td:0"),
         InlineKeyboardButton(f"{_t('d_tomorrow', lang)} ({(today+timedelta(1)).strftime('%m.%d')})", callback_data="td:1")],
        [InlineKeyboardButton(f"{_t('d_3', lang)} ({(today+timedelta(3)).strftime('%m.%d')})", callback_data="td:3"),
         InlineKeyboardButton(f"{_t('d_7', lang)} ({(today+timedelta(7)).strftime('%m.%d')})", callback_data="td:7")],
        [InlineKeyboardButton(_t("custom", lang), callback_data="td:custom")],
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")],
    ]
    a = context.user_data.get("task_assignee", "")
    display = translated or content
    text = f"{_t('task_title', lang)}\n{_t('card_assigned', lang)}: {a}\n{_t('card_task', lang)}: {display}\n\n{_t('sel_deadline', lang)}"
    if translated:
        text += f"\n\n[{_t('original', lang)}] {content}\n[{_t('translated', lang)}] {translated}"
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def cb_task_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    option = query.data.split(":")[1]

    if option == "custom":
        context.user_data["state"] = "awaiting_task_deadline"
        await query.edit_message_text(_t("enter_deadline", lang), reply_markup=_back_kb(lang))
        return

    deadline = (datetime.now(KST).date() + timedelta(days=int(option))).strftime("%Y.%m.%d")
    await _create_task_and_reply(query.from_user.id, context, deadline, query=query)


async def _process_task_deadline_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = _get_user_lang(str(update.effective_user.id))
    deadline = update.message.text.strip()
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', deadline):
        await update.message.reply_text(_t("bad_date", lang), reply_markup=_back_kb(lang))
        return
    context.user_data["state"] = None
    await _create_task_and_reply(update.effective_user.id, context, deadline, message=update.message)


async def _create_task_and_reply(user_id, context, deadline, *, query=None, message=None):
    uid = str(user_id)
    lang = _get_user_lang(uid)
    data = _load_data()
    assignee = context.user_data.get("task_assignee", "")
    content_original = context.user_data.get("task_content", "")
    translated = context.user_data.get("task_translated")
    content = translated or content_original
    creator_name = data["users"].get(uid, {}).get("name", "Unknown")

    task = {
        "id": data["next_id"], "assignee": assignee,
        "content": content, "content_original": content_original if translated else None,
        "deadline": deadline, "status": "대기", "progress": 0,
        "creator": creator_name, "creator_id": uid,
        "created_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "updates": [],
    }
    data["tasks"].append(task)
    data["next_id"] += 1
    _save_data(data)
    context.user_data.clear()

    reply = f"{_t('task_ok', lang)}\n\n{_format_task_card(task, data['users'], lang)}"
    if translated:
        reply += f"\n\n[{_t('original', lang)}] {content_original}\n[{_t('translated', lang)}] {translated}"
    kb = _main_menu_kb(uid, lang)
    if query:
        await query.edit_message_text(reply, reply_markup=kb)
    elif message:
        await message.reply_text(reply, reply_markup=kb)


# ──────────────────────────────────────────
# 📊 전체 현황
# ──────────────────────────────────────────

async def cb_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = _get_user_lang(str(query.from_user.id))
    data = _load_data()
    tasks = data["tasks"]

    if not tasks:
        await query.edit_message_text(_t("no_tasks", lang), reply_markup=_back_refresh_kb(lang))
        return

    active = [t for t in tasks if t["status"] not in ("완료", "취소")]
    done = [t for t in tasks if t["status"] == "완료"]
    cancelled = [t for t in tasks if t["status"] == "취소"]
    lines = [_t("all_title", lang).format(count=len(tasks)) + "\n"]

    if active:
        lines.append(_t("sec_active", lang))
        for t in active:
            lines += [_format_task_card(t, data["users"], lang), ""]
    if done:
        lines.append(_t("sec_done", lang).format(count=len(done)))
        for t in done:
            lines += [_format_task_card(t, data["users"], lang), ""]
    if cancelled:
        lines.append(_t("sec_cancel", lang).format(count=len(cancelled)))
        for t in cancelled:
            lines += [_format_task_card(t, data["users"], lang), ""]

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await query.edit_message_text(text, reply_markup=_back_refresh_kb(lang))


# ──────────────────────────────────────────
# ✅ 완료 처리
# ──────────────────────────────────────────

async def cb_done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    role = _get_user_role(user_id, data)
    if not role:
        await query.edit_message_text(_t("no_role", lang), reply_markup=_back_kb(lang))
        return
    uname = data["users"].get(user_id, {}).get("name", "")
    active = [t for t in data["tasks"] if t["status"] not in ("완료", "취소") and (role == "CEO" or t["assignee"] == uname)]
    if not active:
        await query.edit_message_text(_t("no_done", lang), reply_markup=_back_kb(lang))
        return
    buttons = [[InlineKeyboardButton(f"#{t['id']:03d} {t['content'][:25]}", callback_data=f"do:{t['id']}")] for t in active]
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await query.edit_message_text(
        f"{_t('menu_done', lang)}\n\n{_t('sel_done', lang)}", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    task_id = int(query.data.split(":")[1])
    data = _load_data()
    uname = data["users"].get(user_id, {}).get("name", "")
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await query.edit_message_text(_t("not_found", lang), reply_markup=_back_kb(lang))
        return
    task["status"] = "완료"
    task["progress"] = 100
    task["updates"].append({"date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "content": "완료", "by": uname})
    _save_data(data)
    await query.edit_message_text(
        f"{_t('done_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}",
        reply_markup=_main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# ❌ 업무 취소
# ──────────────────────────────────────────

async def cb_cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    role = _get_user_role(user_id, data)
    if not role:
        await query.edit_message_text(_t("no_role", lang), reply_markup=_back_kb(lang))
        return
    uname = data["users"].get(user_id, {}).get("name", "")
    active = [t for t in data["tasks"] if t["status"] not in ("완료", "취소") and (role == "CEO" or t["assignee"] == uname)]
    if not active:
        await query.edit_message_text(_t("no_cancel", lang), reply_markup=_back_kb(lang))
        return
    buttons = [[InlineKeyboardButton(f"#{t['id']:03d} {t['content'][:25]}", callback_data=f"ca:{t['id']}")] for t in active]
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await query.edit_message_text(
        f"{_t('menu_cancel', lang)}\n\n{_t('sel_cancel', lang)}", reply_markup=InlineKeyboardMarkup(buttons))


async def cb_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    task_id = int(query.data.split(":")[1])
    data = _load_data()
    uname = data["users"].get(user_id, {}).get("name", "")
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await query.edit_message_text(_t("not_found", lang), reply_markup=_back_kb(lang))
        return
    task["status"] = "취소"
    task["updates"].append({"date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "content": "취소", "by": uname})
    _save_data(data)
    await query.edit_message_text(
        f"{_t('cancel_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}",
        reply_markup=_main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 👤 내 업무 + 진행률
# ──────────────────────────────────────────

async def cb_mylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    if not _get_user_role(user_id, data):
        await query.edit_message_text(_t("no_role", lang), reply_markup=_back_kb(lang))
        return
    uname = data["users"][user_id]["name"]
    my = [t for t in data["tasks"] if t["assignee"] == uname]
    if not my:
        await query.edit_message_text(_t("no_my", lang), reply_markup=_back_kb(lang))
        return
    lines = [_t("my_title", lang).format(name=uname, count=len(my)) + "\n"]
    buttons = []
    for t in my:
        lines += [_format_task_card(t, data["users"], lang), ""]
        if t["status"] not in ("완료", "취소"):
            buttons.append([InlineKeyboardButton(
                f"{_t('upd_btn', lang)} #{t['id']:03d}", callback_data=f"up:{t['id']}")])
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def cb_update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = _get_user_lang(str(query.from_user.id))
    task_id = int(query.data.split(":")[1])
    context.user_data["state"] = "awaiting_progress"
    context.user_data["update_task_id"] = task_id
    await query.edit_message_text(
        f"{_t('upd_btn', lang)} #{task_id:03d}\n\n{_t('enter_progress', lang)}",
        reply_markup=_back_kb(lang))


async def _process_progress_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.get("update_task_id")
    if not task_id:
        context.user_data.clear()
        return
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    uname = data["users"].get(user_id, {}).get("name", "")
    text = update.message.text.strip()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(_t("not_found", lang), reply_markup=_back_kb(lang))
        context.user_data.clear()
        return

    translated = None
    if _needs_translation(text):
        translated = await _translate_to_korean(text)

    m = re.search(r'(\d+)\s*%', text)
    if m:
        task["progress"] = int(m.group(1))
        task["status"] = "진행중"
    elif task["status"] == "대기":
        task["status"] = "진행중"

    task["updates"].append({
        "date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "content": translated or text,
        "content_original": text if translated else None, "by": uname})
    _save_data(data)
    context.user_data.clear()

    reply = f"{_t('upd_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}"
    if translated and text != translated:
        reply += f"\n\n[{_t('original', lang)}] {text}\n[{_t('translated', lang)}] {translated}"
    await update.message.reply_text(reply, reply_markup=_main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 📈 보고서 (CEO 전용)
# ──────────────────────────────────────────

async def cb_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await query.edit_message_text(_t("report_only", lang), reply_markup=_back_kb(lang))
        return
    data = _load_data()
    tasks = data["tasks"]
    if not tasks:
        await query.edit_message_text(_t("no_tasks", lang), reply_markup=_back_kb(lang))
        return

    total = len(tasks)
    waiting = len([t for t in tasks if t["status"] == "대기"])
    prog = len([t for t in tasks if t["status"] == "진행중"])
    comp = len([t for t in tasks if t["status"] == "완료"])
    today = datetime.now(KST)

    assignee_stats = {}
    for t in tasks:
        n = t["assignee"]
        if n not in assignee_stats:
            assignee_stats[n] = {"total": 0, "done": 0, "active": 0}
        assignee_stats[n]["total"] += 1
        if t["status"] == "완료":
            assignee_stats[n]["done"] += 1
        else:
            assignee_stats[n]["active"] += 1

    urgent = []
    for t in tasks:
        if t["status"] in ("완료", "취소"):
            continue
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d")
            d = (dl - today).days
            if d <= 3:
                urgent.append((t, d))
        except ValueError:
            pass

    lines = [
        _t("rpt_title", lang), f"Date: {today.strftime('%Y.%m.%d')}\n",
        f"📊 Total: {total}", f"  {_t('st_pending', lang)}: {waiting}",
        f"  {_t('st_progress', lang)}: {prog}", f"  {_t('st_done', lang)}: {comp}",
        f"  Rate: {round(comp/total*100) if total else 0}%", "",
    ]
    for n, s in assignee_stats.items():
        lines.append(f"  {n}: {s['total']} (active {s['active']} / done {s['done']})")
    if urgent:
        lines += ["", "🚨"]
        for t, d in sorted(urgent, key=lambda x: x[1]):
            label = "TODAY!" if d <= 0 else f"{d}d left"
            lines.append(f"  #{t['id']:03d} {t['content']} ({label})")

    await query.edit_message_text("\n".join(lines), reply_markup=_back_kb(lang))


# ──────────────────────────────────────────
# 텍스트 입력 라우터
# ──────────────────────────────────────────

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        _save_group_chat_id(update.effective_chat.id)
    if update.effective_user and not update.effective_user.is_bot:
        _track_user(update.effective_user)


# ──────────────────────────────────────────
# 스케줄 Job — 마감일 알림 (매일 9시 KST)
# ──────────────────────────────────────────

async def _daily_deadline_reminder(context: ContextTypes.DEFAULT_TYPE):
    group_ids = _get_group_chat_ids()
    if not group_ids:
        return
    data = _load_data()
    today = datetime.now(KST).date()
    overdue, due_today, due_tomorrow = [], [], []
    for t in data["tasks"]:
        if t["status"] in ("완료", "취소"):
            continue
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d").date()
        except ValueError:
            continue
        d = (dl - today).days
        if d < 0:
            overdue.append(t)
        elif d == 0:
            due_today.append(t)
        elif d == 1:
            due_tomorrow.append(t)
    if not overdue and not due_today and not due_tomorrow:
        return
    lines = ["⏰ Deadline Alert\n"]
    if overdue:
        lines.append("❌ Overdue!")
        for t in overdue:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}) — {t['deadline']}")
        lines.append("")
    if due_today:
        lines.append("🚨 Due Today!")
        for t in due_today:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']})")
        lines.append("")
    if due_tomorrow:
        lines.append("⚠️ Due Tomorrow!")
        for t in due_tomorrow:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']})")
    text = "\n".join(lines)
    for cid in group_ids:
        try:
            await context.bot.send_message(chat_id=int(cid), text=text)
        except Exception as e:
            print(f"[telegram-bot] 알림 전송 실패 (chat={cid}): {e}", flush=True)


# ──────────────────────────────────────────
# 스케줄 Job — 주간 보고서 (매주 월 9시 KST)
# ──────────────────────────────────────────

async def _generate_weekly_summary(tasks: list) -> str:
    if not ANTHROPIC_API_KEY:
        return ""
    try:
        sd = [{"id": t["id"], "assignee": t["assignee"], "task": t["content"],
               "deadline": t["deadline"], "status": t["status"], "progress": t.get("progress", 0)} for t in tasks]
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        loop = asyncio.get_running_loop()
        msg = await loop.run_in_executor(None, lambda: client.messages.create(
            model="claude-sonnet-4-5", max_tokens=1000,
            system="업무 관리 데이터를 받아서 한국어로 간결한 주간 요약을 작성하세요. 3~5문장으로.",
            messages=[{"role": "user", "content": f"데이터:\n{json.dumps(sd, ensure_ascii=False)}"}]))
        return msg.content[0].text.strip()
    except Exception as e:
        print(f"[telegram-bot] 주간 요약 실패: {e}", flush=True)
        return ""


async def _weekly_report_job(context: ContextTypes.DEFAULT_TYPE):
    group_ids = _get_group_chat_ids()
    if not group_ids:
        return
    data = _load_data()
    tasks = data["tasks"]
    if not tasks:
        return
    active = [t for t in tasks if t["status"] not in ("완료", "취소")]
    completed = [t for t in tasks if t["status"] == "완료"]
    today = datetime.now(KST).date()
    overdue, in_prog = [], []
    for t in active:
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d").date()
            (overdue if dl < today else in_prog).append(t)
        except ValueError:
            in_prog.append(t)
    lines = ["📊 Weekly Report", f"Date: {today.strftime('%Y.%m.%d')}\n",
             f"✅ Done: {len(completed)}", f"🟡 In Progress: {len(in_prog)}", f"❌ Overdue: {len(overdue)}", ""]
    if overdue:
        lines.append("🚨 Overdue")
        for t in overdue:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}) — {t['deadline']}")
        lines.append("")
    if in_prog:
        lines.append("🟡 In Progress")
        for t in in_prog:
            p = f" {t['progress']}%" if t.get("progress") else ""
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}){p}")
        lines.append("")
    ai = await _generate_weekly_summary(tasks)
    if ai:
        lines += ["💡 AI Summary", ai]
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    for cid in group_ids:
        try:
            await context.bot.send_message(chat_id=int(cid), text=text)
        except Exception as e:
            print(f"[telegram-bot] 주간 보고서 실패 (chat={cid}): {e}", flush=True)


# ──────────────────────────────────────────
# 봇 생성 및 실행
# ──────────────────────────────────────────

_bot_app: Application | None = None


async def start_telegram_bot():
    global _bot_app
    if not TELEGRAM_BOT_TOKEN:
        print("[telegram-bot] TELEGRAM_BOT_TOKEN 미설정 — 봇 비활성화", flush=True)
        return

    _bot_app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    _bot_app.add_handler(CommandHandler("start", cmd_start))
    _bot_app.add_handler(CommandHandler("menu", cmd_start))
    _bot_app.add_handler(CommandHandler("resetroles", cmd_resetroles))

    _bot_app.add_handler(CallbackQueryHandler(cb_menu, pattern="^menu$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_lang_start, pattern="^lang$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_set_lang, pattern=r"^setlang:"))
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

    _bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    _bot_app.add_handler(MessageHandler(filters.ChatType.GROUPS, _track_group_chat), group=-1)

    await _bot_app.bot.set_my_commands([
        BotCommand("start", "Main Menu"),
        BotCommand("menu", "Main Menu"),
        BotCommand("resetroles", "Reset Roles (CEO)"),
    ])

    await _bot_app.initialize()
    await _bot_app.start()
    await _bot_app.updater.start_polling(drop_pending_updates=True)

    job_queue = _bot_app.job_queue
    if job_queue:
        job_queue.run_daily(_daily_deadline_reminder, time=dt_time(hour=9, minute=0, tzinfo=KST), name="daily_reminder")
        job_queue.run_daily(_weekly_report_job, time=dt_time(hour=9, minute=0, tzinfo=KST), days=(0,), name="weekly_report")
        print("[telegram-bot] 스케줄 등록: 매일 9시 마감알림 + 매주 월 9시 주간보고", flush=True)
    else:
        print("[telegram-bot] JobQueue 미사용 (APScheduler 미설치)", flush=True)

    print("[telegram-bot] 봇 시작됨 ✅", flush=True)


async def stop_telegram_bot():
    global _bot_app
    if _bot_app:
        await _bot_app.updater.stop()
        await _bot_app.stop()
        await _bot_app.shutdown()
        _bot_app = None
        print("[telegram-bot] 봇 종료됨", flush=True)
