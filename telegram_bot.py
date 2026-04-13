"""
텔레그램 업무관리 봇 — 인라인 키보드 + 다국어 지원
FastAPI와 같은 프로세스에서 실행 / SOL LABS AI 내부 업무 관리용
"""

import os
import json
import re
import asyncio
import threading
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
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

# 데이터 파일 경로 — DATA_DIR 환경변수로 영구 저장 경로 지정 (Railway Volume 등)
_DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent))
_DATA_DIR.mkdir(parents=True, exist_ok=True)
TASKS_FILE = _DATA_DIR / "tasks.json"
LANG_FILE = _DATA_DIR / "users.json"

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
        "task_assigned_notice": "@{assignee} 업무가 배정되었습니다! 👤 내 업무에서 진행상황을 업데이트해주세요 📝",
        "menu_help": "❓ 사용법",
        "help_ceo": "📖 SOL LABS AI 봇 사용법 (CEO)\n\n1️⃣ 업무 등록\n📋 업무 등록 → 담당자 선택 → 내용 입력 → 마감일 선택 → 우선순위 선택\n→ 그룹방에 자동 공개\n\n2️⃣ 전체 현황\n📊 전체 현황 → 전체 업무 목록 (우선순위 순 정렬)\n\n3️⃣ 내 업무\n👤 내 업무 → 본인 배정 업무 확인 + 진행률 업데이트\n\n4️⃣ 업무 수정\n✏️ 업무 수정 → 업무 선택 → 내용/마감일 수정\n\n5️⃣ 담당자 변경\n🔄 담당자 변경 → 업무 선택 → 새 담당자 선택\n\n6️⃣ 업무 검색\n🔍 업무 검색 → 키워드 입력 → 결과 확인\n\n7️⃣ 멤버 관리\n👥 멤버 관리 → 멤버 선택 → 역할 부여\n\n8️⃣ 보고서 / 월간 통계\n📈 전체 보고서 → AI 요약 보고서\n📊 월간 통계 → 이번 달 완료율/지연율\n\n9️⃣ 언어 설정\n🌐 언어 → 원하는 언어 선택",
        "help_member": "📖 SOL LABS AI 봇 사용법\n\n1️⃣ 내 업무 확인\n👤 내 업무 → 배정된 업무 목록 확인\n\n2️⃣ 진행률 업데이트\n👤 내 업무 → 📝 진행률 업데이트 → 숫자% 또는 텍스트 입력\n예시: 50% 또는 \"API 연동 완료\"\n→ 그룹방에 자동 공개\n\n3️⃣ 업무 완료\n✅ 완료 처리 → 완료할 업무 선택\n→ 그룹방에 자동 공개\n\n4️⃣ 언어 설정\n🌐 언어 → 원하는 언어 선택",
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
        # 신규 기능
        "menu_edit": "✏️ 업무 수정", "menu_reassign": "🔄 담당자 변경",
        "menu_search": "🔍 업무 검색",
        "menu_rpt_full": "📈 전체 보고서", "menu_monthly": "📊 월간 통계",
        "st_overdue": "🔴 지연",
        "card_priority": "우선순위",
        "pri_urgent": "🔴 긴급", "pri_normal": "🟡 일반", "pri_low": "🟢 낮음",
        "sel_priority": "우선순위를 선택해주세요:",
        "edit_title": "✏️ 업무 수정", "edit_content": "📝 내용 수정", "edit_deadline": "📅 마감일 수정",
        "edit_ok": "✏️ 업무 #{id} 수정 완료!",
        "enter_edit": "수정할 내용을 입력해주세요:",
        "sel_edit": "수정할 업무를 선택해주세요:",
        "sel_edit_field": "수정할 항목을 선택해주세요:",
        "reassign_title": "🔄 담당자 변경",
        "reassign_ok": "🔄 업무 #{id} 담당자가 @{name}(으)로 변경되었습니다",
        "sel_reassign": "담당자를 변경할 업무를 선택해주세요:",
        "search_title": "🔍 업무 검색", "enter_search": "검색어를 입력해주세요:",
        "search_empty": "🔍 검색 결과가 없습니다.",
        "monthly_title": "📊 이번 달 업무 통계",
        "overdue_auto": "⚠️ 업무 #{id} 마감일이 3일 이상 지났습니다. 확인해주세요!",
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
        "task_assigned_notice": "@{assignee} You have been assigned a task! Please update your progress in 👤 My Tasks 📝",
        "menu_help": "❓ Help",
        "help_ceo": "📖 SOL LABS AI Bot Guide (CEO)\n\n1️⃣ Add Task\n📋 Add Task → Assignee → Description → Deadline → Priority\n→ Posted in group\n\n2️⃣ Status\n📊 Status → All tasks (sorted by priority)\n\n3️⃣ My Tasks\n👤 My Tasks → Your tasks + progress update\n\n4️⃣ Edit Task\n✏️ Edit → Select task → Edit content/deadline\n\n5️⃣ Reassign\n🔄 Reassign → Select task → New assignee\n\n6️⃣ Search\n🔍 Search → Enter keyword → Results\n\n7️⃣ Members\n👥 Members → Select → Assign role\n\n8️⃣ Report / Monthly\n📈 Full Report → AI summary\n📊 Monthly → Completion/overdue rates\n\n9️⃣ Language\n🌐 Language → Select",
        "help_member": "📖 SOL LABS AI Bot Guide\n\n1️⃣ My Tasks\n👤 My Tasks → View assigned tasks\n\n2️⃣ Update Progress\n👤 My Tasks → 📝 Update → Enter % or text\nExample: 50% or \"API done\"\n→ Posted in group\n\n3️⃣ Complete Task\n✅ Done → Select task\n→ Posted in group\n\n4️⃣ Language\n🌐 Language → Select",
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
        "menu_edit": "✏️ Edit Task", "menu_reassign": "🔄 Reassign",
        "menu_search": "🔍 Search",
        "menu_rpt_full": "📈 Full Report", "menu_monthly": "📊 Monthly Stats",
        "st_overdue": "🔴 Overdue",
        "card_priority": "Priority",
        "pri_urgent": "🔴 Urgent", "pri_normal": "🟡 Normal", "pri_low": "🟢 Low",
        "sel_priority": "Select priority:",
        "edit_title": "✏️ Edit Task", "edit_content": "📝 Edit Content", "edit_deadline": "📅 Edit Deadline",
        "edit_ok": "✏️ Task #{id} updated!",
        "enter_edit": "Enter new content:",
        "sel_edit": "Select task to edit:",
        "sel_edit_field": "What to edit:",
        "reassign_title": "🔄 Reassign",
        "reassign_ok": "🔄 Task #{id} reassigned to @{name}",
        "sel_reassign": "Select task to reassign:",
        "search_title": "🔍 Search", "enter_search": "Enter search keyword:",
        "search_empty": "🔍 No results found.",
        "monthly_title": "📊 Monthly Stats",
        "overdue_auto": "⚠️ Task #{id} is 3+ days overdue. Please check!",
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
        "task_assigned_notice": "@{assignee} Вам назначена задача! Обновляйте прогресс в разделе 👤 Мои задачи 📝",
        "menu_help": "❓ Справка",
        "help_ceo": "📖 SOL LABS AI — Руководство (CEO)\n\n1️⃣ Новая задача\n📋 Задача → Исполнитель → Описание → Срок → Приоритет\n→ Публикуется в группе\n\n2️⃣ Статус\n📊 Статус → Все задачи (по приоритету)\n\n3️⃣ Мои задачи\n👤 Мои задачи → Ваши задачи + прогресс\n\n4️⃣ Редактировать\n✏️ Редактировать → Задача → Содержание/срок\n\n5️⃣ Переназначить\n🔄 Переназначить → Задача → Новый исполнитель\n\n6️⃣ Поиск\n🔍 Поиск → Ключевое слово → Результаты\n\n7️⃣ Участники\n👥 Участники → Выбрать → Назначить роль\n\n8️⃣ Отчёт / Статистика\n📈 Полный отчёт → AI сводка\n📊 Месячная → Завершённость/просрочки\n\n9️⃣ Язык\n🌐 Язык → Выберите",
        "help_member": "📖 SOL LABS AI — Руководство\n\n1️⃣ Мои задачи\n👤 Мои задачи → Назначенные задачи\n\n2️⃣ Обновить прогресс\n👤 Мои задачи → 📝 Обновить → Введите % или текст\nПример: 50% или \"API готова\"\n→ Публикуется в группе\n\n3️⃣ Завершить\n✅ Готово → Выберите задачу\n→ Публикуется в группе\n\n4️⃣ Язык\n🌐 Язык → Выберите",
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
        "menu_edit": "✏️ Редактировать", "menu_reassign": "🔄 Переназначить",
        "menu_search": "🔍 Поиск",
        "menu_rpt_full": "📈 Полный отчёт", "menu_monthly": "📊 Месячная статистика",
        "st_overdue": "🔴 Просрочено",
        "card_priority": "Приоритет",
        "pri_urgent": "🔴 Срочно", "pri_normal": "🟡 Обычный", "pri_low": "🟢 Низкий",
        "sel_priority": "Выберите приоритет:",
        "edit_title": "✏️ Редактировать", "edit_content": "📝 Содержание", "edit_deadline": "📅 Срок",
        "edit_ok": "✏️ Задача #{id} обновлена!",
        "enter_edit": "Введите новое содержание:",
        "sel_edit": "Выберите задачу:",
        "sel_edit_field": "Что изменить:",
        "reassign_title": "🔄 Переназначить",
        "reassign_ok": "🔄 Задача #{id} переназначена @{name}",
        "sel_reassign": "Выберите задачу:",
        "search_title": "🔍 Поиск", "enter_search": "Введите ключевое слово:",
        "search_empty": "🔍 Ничего не найдено.",
        "monthly_title": "📊 Месячная статистика",
        "overdue_auto": "⚠️ Задача #{id} просрочена на 3+ дня!",
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
        "task_assigned_notice": "@{assignee} Sizga vazifa tayinlandi! 👤 Mening vazifalarim bo'limida jarayonni yangilang 📝",
        "menu_help": "❓ Yordam",
        "help_ceo": "📖 SOL LABS AI Bot Qo'llanma (CEO)\n\n1️⃣ Vazifa yaratish\n📋 Vazifa → Mas'ul → Tavsif → Muddat → Ustuvorlik\n→ Guruhda e'lon qilinadi\n\n2️⃣ Holat\n📊 Holat → Barcha vazifalar (ustuvorlik bo'yicha)\n\n3️⃣ Mening vazifalarim\n👤 Mening → Vazifalar + jarayon yangilash\n\n4️⃣ Tahrirlash\n✏️ Tahrirlash → Vazifa → Mazmun/muddat\n\n5️⃣ Qayta tayinlash\n🔄 Qayta tayinlash → Vazifa → Yangi mas'ul\n\n6️⃣ Qidirish\n🔍 Qidirish → Kalit so'z → Natijalar\n\n7️⃣ A'zolar\n👥 A'zolar → Tanlang → Rol bering\n\n8️⃣ Hisobot / Oylik\n📈 To'liq hisobot → AI xulosa\n📊 Oylik → Bajarilganlik/kechikish\n\n9️⃣ Til\n🌐 Til → Tanlang",
        "help_member": "📖 SOL LABS AI Bot Qo'llanma\n\n1️⃣ Mening vazifalarim\n👤 Mening → Tayinlangan vazifalar\n\n2️⃣ Jarayonni yangilash\n👤 Mening → 📝 Yangilash → % yoki matn kiriting\nMisol: 50% yoki \"API tayyor\"\n→ Guruhda e'lon qilinadi\n\n3️⃣ Yakunlash\n✅ Bajarildi → Vazifani tanlang\n→ Guruhda e'lon qilinadi\n\n4️⃣ Til\n🌐 Til → Tanlang",
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
        "menu_edit": "✏️ Tahrirlash", "menu_reassign": "🔄 Qayta tayinlash",
        "menu_search": "🔍 Qidirish",
        "menu_rpt_full": "📈 To'liq hisobot", "menu_monthly": "📊 Oylik statistika",
        "st_overdue": "🔴 Kechikkan",
        "card_priority": "Ustuvorlik",
        "pri_urgent": "🔴 Shoshilinch", "pri_normal": "🟡 Oddiy", "pri_low": "🟢 Past",
        "sel_priority": "Ustuvorlikni tanlang:",
        "edit_title": "✏️ Tahrirlash", "edit_content": "📝 Mazmun", "edit_deadline": "📅 Muddat",
        "edit_ok": "✏️ Vazifa #{id} yangilandi!",
        "enter_edit": "Yangi mazmunni kiriting:",
        "sel_edit": "Vazifani tanlang:",
        "sel_edit_field": "Nimani o'zgartirish:",
        "reassign_title": "🔄 Qayta tayinlash",
        "reassign_ok": "🔄 Vazifa #{id} @{name}ga tayinlandi",
        "sel_reassign": "Vazifani tanlang:",
        "search_title": "🔍 Qidirish", "enter_search": "Kalit so'zni kiriting:",
        "search_empty": "🔍 Natija topilmadi.",
        "monthly_title": "📊 Oylik statistika",
        "overdue_auto": "⚠️ Vazifa #{id} 3+ kun kechikkan!",
    },
}

# 내부 상태값 → 번역 키 매핑
_STATUS_KEY = {"대기": "st_pending", "진행중": "st_progress", "완료": "st_done", "취소": "st_cancelled", "지연": "st_overdue"}
_PRI_ORDER = {"urgent": 0, "normal": 1, "low": 2, "": 3}


def _t(key: str, lang: str = "ko") -> str:
    """번역 키 → 해당 언어 텍스트 (fallback: 한국어)"""
    return _T.get(lang, _T["ko"]).get(key, _T["ko"].get(key, key))


# ──────────────────────────────────────────
# 데이터 저장/로드 (파일 잠금으로 동시 쓰기 방지)
# ──────────────────────────────────────────

_data_lock = threading.Lock()
_lang_lock = threading.Lock()


def _load_data() -> dict:
    with _data_lock:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"next_id": 1, "users": {}, "tasks": []}


def _save_data(data: dict):
    with _data_lock:
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _load_lang() -> dict:
    with _lang_lock:
        if LANG_FILE.exists():
            with open(LANG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def _save_lang(prefs: dict):
    with _lang_lock:
        with open(LANG_FILE, "w", encoding="utf-8") as f:
            json.dump(prefs, f, ensure_ascii=False, indent=2)


def _get_user_lang(user_id) -> str:
    prefs = _load_lang()
    return prefs.get(str(user_id), "ko")


def _set_user_lang(user_id, lang: str):
    prefs = _load_lang()
    prefs[str(user_id)] = lang
    _save_lang(prefs)


# ──────────────────────────────────────────
# 영구 대화 상태 (서버 재시작에도 유지)
# ──────────────────────────────────────────

def _get_conv(user_id: str) -> dict:
    """users.json에서 대화 상태 로드"""
    prefs = _load_lang()
    return prefs.get(f"_conv:{user_id}", {})


def _save_conv(user_id: str, conv: dict):
    """users.json에 대화 상태 저장"""
    fresh = _load_lang()
    if conv:
        fresh[f"_conv:{user_id}"] = conv
    else:
        fresh.pop(f"_conv:{user_id}", None)
    _save_lang(fresh)


def _set_state(context, user_id: str, **kv):
    """대화 상태를 메모리 + 파일 양쪽에 저장"""
    for k, v in kv.items():
        if v is None:
            context.user_data.pop(k, None)
        else:
            context.user_data[k] = v
    # 파일에도 영구 저장
    conv = {k: v for k, v in context.user_data.items() if v is not None}
    _save_conv(user_id, conv)
    print(f"[state] user={user_id} set → {kv}", flush=True)


def _clear_state(context, user_id: str):
    """대화 상태 초기화 (group_chat_id 보존)"""
    gcid = context.user_data.get("group_chat_id")
    context.user_data.clear()
    if gcid:
        context.user_data["group_chat_id"] = gcid
    _save_conv(user_id, {"group_chat_id": gcid} if gcid else {})
    print(f"[state] user={user_id} cleared", flush=True)


def _restore_state(context, user_id: str):
    """서버 재시작 후 파일에서 대화 상태 복원"""
    if not context.user_data.get("state"):
        conv = _get_conv(user_id)
        if conv.get("state"):
            context.user_data.update(conv)
            print(f"[state] user={user_id} restored → state={conv.get('state')}", flush=True)


def _save_group_chat_id(chat_id: int):
    cid = str(chat_id)
    with _data_lock:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"next_id": 1, "users": {}, "tasks": []}
        if "group_chat_ids" not in data:
            data["group_chat_ids"] = []
        if cid not in data["group_chat_ids"]:
            data["group_chat_ids"].append(cid)
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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
        with _data_lock:
            if TASKS_FILE.exists():
                with open(TASKS_FILE, "r", encoding="utf-8") as f:
                    fresh = json.load(f)
            else:
                fresh = {"next_id": 1, "users": {}, "tasks": []}
            fresh["users"][uid] = {"name": name, "role": "CEO", "username": username}
            with open(TASKS_FILE, "w", encoding="utf-8") as f:
                json.dump(fresh, f, ensure_ascii=False, indent=2)
        data["users"][uid] = fresh["users"][uid]
    return data


def _track_user(user):
    uid = str(user.id)
    name = user.full_name or user.username or "Unknown"
    username = user.username or ""
    # 파일 잠금 내에서 읽기 → 수정 → 쓰기 원자적 수행
    with _data_lock:
        if TASKS_FILE.exists():
            with open(TASKS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {"next_id": 1, "users": {}, "tasks": []}
        if "known_users" not in data:
            data["known_users"] = {}
        existing = data["known_users"].get(uid)
        if existing and existing.get("name") == name:
            return  # 변경 없음
        data["known_users"][uid] = {"name": name, "username": username}
        with open(TASKS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


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

    pri = task.get("priority", "")
    pri_line = ""
    if pri:
        pri_key = {"urgent": "pri_urgent", "normal": "pri_normal", "low": "pri_low"}.get(pri)
        if pri_key:
            pri_line = f"\n{_t('card_priority', lang)}: {_t(pri_key, lang)}"

    return (
        f"📋 #{task['id']:03d}{pri_line}\n"
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
    if is_admin:
        buttons = [
            [InlineKeyboardButton(_t("menu_task", L), callback_data="task"),
             InlineKeyboardButton(_t("menu_status", L), callback_data="list")],
            [InlineKeyboardButton(_t("menu_done", L), callback_data="done"),
             InlineKeyboardButton(_t("menu_cancel", L), callback_data="cancel_menu")],
            [InlineKeyboardButton(_t("menu_edit", L), callback_data="edit"),
             InlineKeyboardButton(_t("menu_reassign", L), callback_data="reassign")],
            [InlineKeyboardButton(_t("menu_my", L), callback_data="mylist"),
             InlineKeyboardButton(_t("menu_search", L), callback_data="search")],
            [InlineKeyboardButton(_t("menu_rpt_full", L), callback_data="report"),
             InlineKeyboardButton(_t("menu_monthly", L), callback_data="monthly")],
            [InlineKeyboardButton(_t("menu_members", L), callback_data="members"),
             InlineKeyboardButton(_t("menu_lang", L), callback_data="lang")],
            [InlineKeyboardButton(_t("menu_help", L), callback_data="help")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton(_t("menu_status", L), callback_data="list")],
            [InlineKeyboardButton(_t("menu_done", L), callback_data="done"),
             InlineKeyboardButton(_t("menu_cancel", L), callback_data="cancel_menu")],
            [InlineKeyboardButton(_t("menu_my", L), callback_data="mylist"),
             InlineKeyboardButton(_t("menu_lang", L), callback_data="lang")],
            [InlineKeyboardButton(_t("menu_help", L), callback_data="help")],
        ]
    return InlineKeyboardMarkup(buttons)


def _back_kb(lang: str = "ko"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")]
    ])


_REPLY_HINT = {
    "ko": "(이 메시지에 답장으로 입력해주세요 💬)",
    "en": "(Reply to this message to enter 💬)",
    "ru": "(Ответьте на это сообщение 💬)",
    "uz": "(Bu xabarga javob yozing 💬)",
}

_DM_HINT = {
    "ko": "개인 메시지를 먼저 시작해주세요 → @{bot} 클릭 후 /start",
    "en": "Please start a DM first → Click @{bot} then /start",
    "ru": "Сначала начните личный чат → @{bot}, затем /start",
    "uz": "Avval shaxsiy xabar boshlang → @{bot} bosing, /start",
}


def _back_refresh_kb(lang: str = "ko"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(_t("menu_refresh", lang), callback_data="list"),
         InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")]
    ])


# ──────────────────────────────────────────
# DM 전송 헬퍼
# ──────────────────────────────────────────

def _is_group(chat) -> bool:
    return chat.type in ("group", "supergroup")


async def _dm(query, context, text: str, reply_markup=None) -> bool:
    """콜백 응답을 DM으로 전송. 그룹이면 DM 전송 + 그룹 버튼 제거. DM이면 메시지 편집."""
    uid = query.from_user.id
    chat = query.message.chat

    if _is_group(chat):
        context.user_data["group_chat_id"] = chat.id
        try:
            await context.bot.send_message(chat_id=uid, text=text, reply_markup=reply_markup)
        except Exception:
            lang = _get_user_lang(str(uid))
            bot_un = context.bot.username or "bot"
            await query.answer(_DM_HINT.get(lang, _DM_HINT["ko"]).format(bot=bot_un), show_alert=True)
            return False
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return True
    else:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception:
            await context.bot.send_message(chat_id=uid, text=text, reply_markup=reply_markup)
        return True


async def _dm_prompt(query, context, prompt: str, lang: str) -> bool:
    """텍스트 입력 요청을 DM ForceReply로 전송"""
    uid = query.from_user.id
    chat = query.message.chat
    hint = _REPLY_HINT.get(lang, _REPLY_HINT["ko"])
    full = f"{prompt}\n{hint}\n\n/menu — {_t('menu_home', lang)}"

    if _is_group(chat):
        context.user_data["group_chat_id"] = chat.id
        try:
            await context.bot.send_message(chat_id=uid, text=full, reply_markup=ForceReply(selective=True))
        except Exception:
            bot_un = context.bot.username or "bot"
            await query.answer(_DM_HINT.get(lang, _DM_HINT["ko"]).format(bot=bot_un), show_alert=True)
            return False
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        return True
    else:
        try:
            await query.edit_message_text("⏳")
        except Exception:
            pass
        await context.bot.send_message(chat_id=uid, text=full, reply_markup=ForceReply(selective=True))
        return True


async def _dm_prompt_msg(message, prompt: str, lang: str):
    """텍스트→텍스트 전환 시 DM ForceReply"""
    hint = _REPLY_HINT.get(lang, _REPLY_HINT["ko"])
    await message.reply_text(
        f"{prompt}\n{hint}\n\n/menu — {_t('menu_home', lang)}",
        reply_markup=ForceReply(selective=True))


async def _post_group(context, group_chat_id, text: str):
    """그룹에 공개 메시지 전송"""
    if not group_chat_id:
        return
    try:
        await context.bot.send_message(chat_id=int(group_chat_id), text=text)
    except Exception as e:
        print(f"[telegram-bot] 그룹 전송 실패: {e}", flush=True)


# ──────────────────────────────────────────
# /start, /menu — 메인 메뉴
# ──────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    _clear_state(context, user_id)
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
    user_id = str(query.from_user.id)
    _clear_state(context, user_id)
    lang = _get_user_lang(user_id)
    data = _load_data()

    if _is_admin(user_id):
        data = _ensure_admin_in_data(query.from_user, data)

    role = _get_user_role(user_id, data)
    if not role:
        await _dm(query, context, _t("no_role", lang), _back_kb(lang))
        return

    name = data["users"][user_id]["name"]
    await _dm(query, context,
        f"{_t('welcome', lang)}\n{name} ({role})",
        _main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 🌐 언어 선택
# ──────────────────────────────────────────

async def cb_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """사용법 안내 — CEO/일반 멤버 구분"""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    key = "help_ceo" if _is_admin(user_id) else "help_member"
    await _dm(query, context, _t(key, lang), _back_kb(lang))


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
    await _dm(query, context, _t("sel_lang", lang), InlineKeyboardMarkup(buttons))


async def cb_set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    new_lang = query.data.split(":")[1]
    _set_user_lang(user_id, new_lang)
    await _dm(query, context,
        _t("lang_set", new_lang), _main_menu_kb(user_id, new_lang))


# ──────────────────────────────────────────
# 👥 멤버 관리 (CEO 전용)
# ──────────────────────────────────────────

async def cb_members_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)

    if not _is_admin(user_id):
        await _dm(query, context, _t("members_only", lang), _back_kb(lang))
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
    await _dm(query, context, "\n".join(lines), InlineKeyboardMarkup(buttons))


async def cb_member_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)

    if not _is_admin(user_id):
        await _dm(query, context, _t("no_perm", lang), _back_kb(lang))
        return

    target_uid = query.data.split(":")[1]
    data = _load_data()
    target_info = data.get("known_users", {}).get(target_uid)
    if not target_info:
        await _dm(query, context, _t("mem_404", lang), _back_kb(lang))
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
    await _dm(query, context,
        f"{_t('mem_title', lang)}\n\n{_t('mem_sel_role', lang).format(name=name)}",
        InlineKeyboardMarkup(buttons))


async def cb_assign_role(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    admin_id = str(query.from_user.id)
    lang = _get_user_lang(admin_id)

    if not _is_admin(admin_id):
        await _dm(query, context, _t("no_perm", lang), _back_kb(lang))
        return

    parts = query.data.split(":")
    target_uid, role = parts[1], parts[2]
    data = _load_data()
    target_info = data.get("known_users", {}).get(target_uid)
    if not target_info:
        await _dm(query, context, _t("mem_404", lang), _back_kb(lang))
        return

    name = target_info["name"]
    data["users"][target_uid] = {"name": name, "role": role, "username": target_info.get("username", "")}
    _save_data(data)
    await _dm(query, context,
        _t("mem_ok", lang).format(name=name, role=role),
        _main_menu_kb(admin_id, lang))


async def cmd_debug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/debug — CEO 전용, tasks.json 원본 데이터 출력"""
    user_id = str(update.effective_user.id)
    if not _is_admin(user_id):
        await update.message.reply_text("❌ CEO only")
        return
    data = _load_data()
    users = data.get("users", {})
    known = data.get("known_users", {})
    groups = data.get("group_chat_ids", [])

    lines = [
        f"🔍 DEBUG — {TASKS_FILE}",
        f"📁 DATA_DIR: {_DATA_DIR}",
        f"📄 File exists: {TASKS_FILE.exists()}",
        "",
        f"👥 users ({len(users)}):",
    ]
    for uid, u in users.items():
        lines.append(f"  [{uid}] {u.get('name')} — role={u.get('role')!r}")
    lines.append(f"\n👤 known_users ({len(known)}):")
    for uid, u in known.items():
        lines.append(f"  [{uid}] {u.get('name')}")
    lines.append(f"\n💬 groups: {groups}")
    lines.append(f"📋 tasks: {len(data.get('tasks', []))}건")

    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await update.message.reply_text(text)


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
# 📋 업무 등록 플로우 (DM에서 진행, 완료 시 그룹 공개)
# ──────────────────────────────────────────

async def cb_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)

    # CEO 전용
    if not _is_admin(user_id):
        await _dm(query, context, _t("no_perm", lang), _back_kb(lang))
        return

    # 최신 데이터를 반드시 파일에서 읽기
    data = _load_data()

    # CEO가 data에 없으면 자동 등록
    if user_id not in data["users"]:
        data = _ensure_admin_in_data(query.from_user, data)
        data = _load_data()  # 저장 후 다시 읽기

    if not _get_user_role(user_id, data):
        await _dm(query, context, _t("no_role", lang), _back_kb(lang))
        return

    # 역할이 있는 모든 유저를 담당자 목록에 표시
    all_users = data.get("users", {})
    members = {uid: uinfo for uid, uinfo in all_users.items() if uinfo.get("role")}
    skipped = {uid: uinfo for uid, uinfo in all_users.items() if not uinfo.get("role")}
    print(f"[task-start] 전체 users={len(all_users)} → 표시={len(members)} 제외={len(skipped)}", flush=True)
    for uid, u in all_users.items():
        print(f"  [{uid}] name={u.get('name')} role={u.get('role')!r}", flush=True)

    buttons = []
    row = []
    for uid, uinfo in members.items():
        row.append(InlineKeyboardButton(uinfo["name"], callback_data=f"ta:{uid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(_t("custom", lang), callback_data="ta:custom")])
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await _dm(query, context,
        f"{_t('task_title', lang)}\n\n{_t('sel_assignee', lang)}",
        InlineKeyboardMarkup(buttons))


async def cb_task_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    assignee_key = query.data.split(":")[1]

    if assignee_key == "custom":
        _set_state(context, user_id, state="awaiting_task_assignee")
        await _dm_prompt(query, context,
            f"{_t('task_title', lang)}\n\n{_t('enter_assignee', lang)}", lang)
        return

    data = _load_data()
    a = data["users"].get(assignee_key, {}).get("name", assignee_key)
    _set_state(context, user_id, state="awaiting_task_content", task_assignee=a)
    await _dm_prompt(query, context,
        f"{_t('task_title', lang)}\n{_t('card_assigned', lang)}: {a}\n\n{_t('enter_content', lang)}", lang)


async def _process_task_assignee_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    name = update.message.text.strip()
    _set_state(context, user_id, state="awaiting_task_content", task_assignee=name)
    await _dm_prompt_msg(update.message,
        f"{_t('task_title', lang)}\n{_t('card_assigned', lang)}: {name}\n\n{_t('enter_content', lang)}", lang)


async def _process_task_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    content = update.message.text.strip()
    print(f"[task-content] user={user_id} content='{content[:50]}'", flush=True)

    # 상태를 "마감일 대기"로 전환 (번역 중 서버 재시작 대비)
    _set_state(context, user_id, state="awaiting_deadline_btn", task_content=content)

    translated = None
    if _needs_translation(content):
        translated = await _translate_to_korean(content)
        if translated:
            _set_state(context, user_id, task_translated=translated)

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
        _set_state(context, user_id, state="awaiting_task_deadline")
        await _dm_prompt(query, context, _t("enter_deadline", lang), lang)
        return

    deadline = (datetime.now(KST).date() + timedelta(days=int(option))).strftime("%Y.%m.%d")
    _set_state(context, user_id, task_deadline=deadline, state=None)
    await _show_priority_buttons(query, context, user_id, lang)


async def _show_priority_buttons(query, context, user_id, lang):
    """우선순위 선택 버튼 표시"""
    buttons = [
        [InlineKeyboardButton(_t("pri_urgent", lang), callback_data="tp:urgent"),
         InlineKeyboardButton(_t("pri_normal", lang), callback_data="tp:normal"),
         InlineKeyboardButton(_t("pri_low", lang), callback_data="tp:low")],
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")],
    ]
    await _dm(query, context, _t("sel_priority", lang), InlineKeyboardMarkup(buttons))


async def cb_task_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """우선순위 선택 → 업무 생성"""
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    priority = query.data.split(":")[1]
    _set_state(context, user_id, task_priority=priority)
    deadline = context.user_data.get("task_deadline", "")
    await _create_task_and_reply(query.from_user.id, context, deadline, query=query)


async def _process_task_deadline_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    deadline = update.message.text.strip()
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', deadline):
        _set_state(context, user_id, state="awaiting_task_deadline")
        await _dm_prompt_msg(update.message, _t("bad_date", lang) + "\n" + _t("enter_deadline", lang), lang)
        return
    _set_state(context, user_id, task_deadline=deadline, state=None)
    # 우선순위 버튼 표시
    buttons = [
        [InlineKeyboardButton(_t("pri_urgent", lang), callback_data="tp:urgent"),
         InlineKeyboardButton(_t("pri_normal", lang), callback_data="tp:normal"),
         InlineKeyboardButton(_t("pri_low", lang), callback_data="tp:low")],
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")],
    ]
    await update.message.reply_text(_t("sel_priority", lang), reply_markup=InlineKeyboardMarkup(buttons))


async def _create_task_and_reply(user_id, context, deadline, *, query=None, message=None):
    """업무 생성 — DM 확인 + 그룹 공개"""
    uid = str(user_id)
    lang = _get_user_lang(uid)
    data = _load_data()
    assignee = context.user_data.get("task_assignee", "")
    content_original = context.user_data.get("task_content", "")
    translated = context.user_data.get("task_translated")
    content = translated or content_original
    creator_name = data["users"].get(uid, {}).get("name", "Unknown")
    gcid = context.user_data.get("group_chat_id")

    priority = context.user_data.get("task_priority", "normal")
    task = {
        "id": data["next_id"], "assignee": assignee,
        "content": content, "content_original": content_original if translated else None,
        "deadline": deadline, "status": "대기", "progress": 0, "priority": priority,
        "creator": creator_name, "creator_id": uid,
        "created_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "updates": [],
    }
    data["tasks"].append(task)
    data["next_id"] += 1
    _save_data(data)

    # DM 확인
    reply = f"{_t('task_ok', lang)}\n\n{_format_task_card(task, data['users'], lang)}"
    if translated:
        reply += f"\n\n[{_t('original', lang)}] {content_original}\n[{_t('translated', lang)}] {translated}"
    kb = _main_menu_kb(uid, lang)
    if query:
        await _dm(query, context, reply, kb)
    elif message:
        await message.reply_text(reply, reply_markup=kb)

    # 그룹에 업무카드 공개 + 담당자 멘션 안내
    card = _format_task_card(task, data['users'], 'ko')
    notice = _t("task_assigned_notice", "ko").format(assignee=assignee)
    group_msg = f"{_t('task_ok', 'ko')}\n\n{card}\n\n{notice}"
    await _post_group(context, gcid, group_msg)

    # 모든 그룹에도 전송 (gcid가 없거나 다른 그룹 대비)
    if not gcid:
        for cid in _get_group_chat_ids():
            await _post_group(context, int(cid), group_msg)

    _clear_state(context, uid)


# ──────────────────────────────────────────
# 📊 전체 현황 (DM)
# ──────────────────────────────────────────

async def cb_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = _get_user_lang(str(query.from_user.id))
    data = _load_data()
    tasks = data["tasks"]

    if not tasks:
        await _dm(query, context, _t("no_tasks", lang), _back_refresh_kb(lang))
        return

    active = sorted(
        [t for t in tasks if t["status"] not in ("완료", "취소")],
        key=lambda t: _PRI_ORDER.get(t.get("priority", ""), 3))
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
    await _dm(query, context, text, _back_refresh_kb(lang))


# ──────────────────────────────────────────
# ✅ 완료 처리 (DM 선택, 그룹 공개)
# ──────────────────────────────────────────

async def cb_done_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    role = _get_user_role(user_id, data)
    if not role:
        await _dm(query, context, _t("no_role", lang), _back_kb(lang))
        return
    uname = data["users"].get(user_id, {}).get("name", "")
    active = [t for t in data["tasks"] if t["status"] not in ("완료", "취소") and (role == "CEO" or t["assignee"] == uname)]
    if not active:
        await _dm(query, context, _t("no_done", lang), _back_kb(lang))
        return
    buttons = [[InlineKeyboardButton(f"#{t['id']:03d} {t['content'][:25]}", callback_data=f"do:{t['id']}")] for t in active]
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await _dm(query, context,
        f"{_t('menu_done', lang)}\n\n{_t('sel_done', lang)}", InlineKeyboardMarkup(buttons))


async def cb_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    task_id = int(query.data.split(":")[1])
    data = _load_data()
    uname = data["users"].get(user_id, {}).get("name", "")
    gcid = context.user_data.get("group_chat_id")

    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await _dm(query, context, _t("not_found", lang), _back_kb(lang))
        return
    task["status"] = "완료"
    task["progress"] = 100
    task["updates"].append({"date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "content": "완료", "by": uname})
    _save_data(data)

    # DM 확인
    await _dm(query, context,
        f"{_t('done_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}",
        _main_menu_kb(user_id, lang))

    # 그룹 공개
    await _post_group(context, gcid,
        f"🟢 Task #{task_id:03d} Done!\n\n{_format_task_card(task, data['users'], 'ko')}")


# ──────────────────────────────────────────
# ❌ 업무 취소 (DM)
# ──────────────────────────────────────────

async def cb_cancel_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    role = _get_user_role(user_id, data)
    if not role:
        await _dm(query, context, _t("no_role", lang), _back_kb(lang))
        return
    uname = data["users"].get(user_id, {}).get("name", "")
    active = [t for t in data["tasks"] if t["status"] not in ("완료", "취소") and (role == "CEO" or t["assignee"] == uname)]
    if not active:
        await _dm(query, context, _t("no_cancel", lang), _back_kb(lang))
        return
    buttons = [[InlineKeyboardButton(f"#{t['id']:03d} {t['content'][:25]}", callback_data=f"ca:{t['id']}")] for t in active]
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await _dm(query, context,
        f"{_t('menu_cancel', lang)}\n\n{_t('sel_cancel', lang)}", InlineKeyboardMarkup(buttons))


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
        await _dm(query, context, _t("not_found", lang), _back_kb(lang))
        return
    task["status"] = "취소"
    task["updates"].append({"date": datetime.now(KST).strftime("%Y-%m-%d %H:%M"), "content": "취소", "by": uname})
    _save_data(data)
    await _dm(query, context,
        f"{_t('cancel_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}",
        _main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 👤 내 업무 + 진행률 (DM)
# ──────────────────────────────────────────

async def cb_mylist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    data = _load_data()
    if not _get_user_role(user_id, data):
        await _dm(query, context, _t("no_role", lang), _back_kb(lang))
        return
    uname = data["users"][user_id]["name"]
    my = [t for t in data["tasks"] if t["assignee"] == uname]
    if not my:
        await _dm(query, context, _t("no_my", lang), _back_kb(lang))
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
    await _dm(query, context, text, InlineKeyboardMarkup(buttons))


async def cb_update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    lang = _get_user_lang(str(query.from_user.id))
    task_id = int(query.data.split(":")[1])
    _set_state(context, str(query.from_user.id), state="awaiting_progress", update_task_id=task_id)
    await _dm_prompt(query, context,
        f"{_t('upd_btn', lang)} #{task_id:03d}\n\n{_t('enter_progress', lang)}", lang)


async def _process_progress_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    task_id = context.user_data.get("update_task_id")
    if not task_id:
        _clear_state(context, user_id)
        return
    lang = _get_user_lang(user_id)
    data = _load_data()
    uname = data["users"].get(user_id, {}).get("name", "")
    text = update.message.text.strip()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(_t("not_found", lang), reply_markup=_back_kb(lang))
        _clear_state(context, user_id)
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
    gcid = context.user_data.get("group_chat_id")
    _clear_state(context, user_id)

    # DM 확인
    reply = f"{_t('upd_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}"
    if translated and text != translated:
        reply += f"\n\n[{_t('original', lang)}] {text}\n[{_t('translated', lang)}] {translated}"
    await update.message.reply_text(reply, reply_markup=_main_menu_kb(user_id, lang))

    # 그룹방 공개
    group_msg = f"🔄 {_t('upd_ok', 'ko').format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], 'ko')}"
    await _post_group(context, gcid, group_msg)
    if not gcid:
        for cid in _get_group_chat_ids():
            await _post_group(context, int(cid), group_msg)


# ──────────────────────────────────────────
# ✏️ 업무 수정 (CEO 전용)
# ──────────────────────────────────────────

async def cb_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await _dm(query, context, _t("no_perm", lang), _back_kb(lang))
        return
    data = _load_data()
    active = [t for t in data["tasks"] if t["status"] not in ("완료", "취소")]
    if not active:
        await _dm(query, context, _t("no_tasks", lang), _back_kb(lang))
        return
    buttons = [[InlineKeyboardButton(f"#{t['id']:03d} {t['content'][:25]}", callback_data=f"ed:{t['id']}")] for t in active]
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await _dm(query, context, f"{_t('edit_title', lang)}\n\n{_t('sel_edit', lang)}", InlineKeyboardMarkup(buttons))


async def cb_edit_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    task_id = int(query.data.split(":")[1])
    _set_state(context, user_id, edit_task_id=task_id)
    buttons = [
        [InlineKeyboardButton(_t("edit_content", lang), callback_data=f"edf:content"),
         InlineKeyboardButton(_t("edit_deadline", lang), callback_data=f"edf:deadline")],
        [InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")],
    ]
    await _dm(query, context, f"{_t('edit_title', lang)} #{task_id:03d}\n\n{_t('sel_edit_field', lang)}", InlineKeyboardMarkup(buttons))


async def cb_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    field = query.data.split(":")[1]
    if field == "content":
        _set_state(context, user_id, state="awaiting_edit_content")
        await _dm_prompt(query, context, _t("enter_edit", lang), lang)
    elif field == "deadline":
        _set_state(context, user_id, state="awaiting_edit_deadline")
        await _dm_prompt(query, context, _t("enter_deadline", lang), lang)


async def _process_edit_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    task_id = context.user_data.get("edit_task_id")
    if not task_id:
        _clear_state(context, user_id)
        return
    new_content = update.message.text.strip()
    translated = None
    if _needs_translation(new_content):
        translated = await _translate_to_korean(new_content)
    data = _load_data()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(_t("not_found", lang), reply_markup=_back_kb(lang))
        _clear_state(context, user_id)
        return
    task["content"] = translated or new_content
    _save_data(data)
    gcid = context.user_data.get("group_chat_id")
    _clear_state(context, user_id)
    reply = f"{_t('edit_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}"
    await update.message.reply_text(reply, reply_markup=_main_menu_kb(user_id, lang))
    await _post_group(context, gcid, f"{_t('edit_ok', 'ko').format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], 'ko')}")
    if not gcid:
        for cid in _get_group_chat_ids():
            await _post_group(context, int(cid), f"{_t('edit_ok', 'ko').format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], 'ko')}")


async def _process_edit_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    task_id = context.user_data.get("edit_task_id")
    if not task_id:
        _clear_state(context, user_id)
        return
    deadline = update.message.text.strip()
    if not re.match(r'^\d{4}\.\d{2}\.\d{2}$', deadline):
        _set_state(context, user_id, state="awaiting_edit_deadline")
        await _dm_prompt_msg(update.message, _t("bad_date", lang), lang)
        return
    data = _load_data()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    if not task:
        await update.message.reply_text(_t("not_found", lang), reply_markup=_back_kb(lang))
        _clear_state(context, user_id)
        return
    task["deadline"] = deadline
    _save_data(data)
    gcid = context.user_data.get("group_chat_id")
    _clear_state(context, user_id)
    reply = f"{_t('edit_ok', lang).format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], lang)}"
    await update.message.reply_text(reply, reply_markup=_main_menu_kb(user_id, lang))
    await _post_group(context, gcid, f"{_t('edit_ok', 'ko').format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], 'ko')}")
    if not gcid:
        for cid in _get_group_chat_ids():
            await _post_group(context, int(cid), f"{_t('edit_ok', 'ko').format(id=f'{task_id:03d}')}\n\n{_format_task_card(task, data['users'], 'ko')}")


# ──────────────────────────────────────────
# 🔄 담당자 변경 (CEO 전용)
# ──────────────────────────────────────────

async def cb_reassign_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await _dm(query, context, _t("no_perm", lang), _back_kb(lang))
        return
    data = _load_data()
    active = [t for t in data["tasks"] if t["status"] not in ("완료", "취소")]
    if not active:
        await _dm(query, context, _t("no_tasks", lang), _back_kb(lang))
        return
    buttons = [[InlineKeyboardButton(f"#{t['id']:03d} {t['content'][:20]} (@{t['assignee']})", callback_data=f"ra:{t['id']}")] for t in active]
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await _dm(query, context, f"{_t('reassign_title', lang)}\n\n{_t('sel_reassign', lang)}", InlineKeyboardMarkup(buttons))


async def cb_reassign_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    task_id = int(query.data.split(":")[1])
    _set_state(context, user_id, reassign_task_id=task_id)
    data = _load_data()
    buttons = []
    row = []
    for uid, uinfo in data["users"].items():
        if uinfo.get("role"):
            row.append(InlineKeyboardButton(uinfo["name"], callback_data=f"rm:{uid}"))
            if len(row) == 2:
                buttons.append(row)
                row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(_t("menu_home", lang), callback_data="menu")])
    await _dm(query, context, f"{_t('reassign_title', lang)} #{task_id:03d}\n\n{_t('sel_assignee', lang)}", InlineKeyboardMarkup(buttons))


async def cb_reassign_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    new_uid = query.data.split(":")[1]
    task_id = context.user_data.get("reassign_task_id")
    if not task_id:
        await _dm(query, context, _t("not_found", lang), _back_kb(lang))
        return
    data = _load_data()
    task = next((t for t in data["tasks"] if t["id"] == task_id), None)
    new_name = data["users"].get(new_uid, {}).get("name", "")
    if not task or not new_name:
        await _dm(query, context, _t("not_found", lang), _back_kb(lang))
        _clear_state(context, user_id)
        return
    task["assignee"] = new_name
    _save_data(data)
    gcid = context.user_data.get("group_chat_id")
    _clear_state(context, user_id)
    msg = _t("reassign_ok", lang).format(id=f"{task_id:03d}", name=new_name)
    await _dm(query, context, f"{msg}\n\n{_format_task_card(task, data['users'], lang)}", _main_menu_kb(user_id, lang))
    # 그룹 공개
    gmsg = _t("reassign_ok", "ko").format(id=f"{task_id:03d}", name=new_name)
    await _post_group(context, gcid, gmsg)
    if not gcid:
        for cid in _get_group_chat_ids():
            await _post_group(context, int(cid), gmsg)
    # 새 담당자 DM
    try:
        new_lang = _get_user_lang(new_uid)
        notice = f"📋 #{task_id:03d}\n{_t('task_assigned_notice', new_lang).format(assignee=new_name)}"
        await context.bot.send_message(chat_id=int(new_uid), text=notice)
    except Exception:
        pass


# ──────────────────────────────────────────
# 🔍 업무 검색 (CEO 전용)
# ──────────────────────────────────────────

async def cb_search_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await _dm(query, context, _t("no_perm", lang), _back_kb(lang))
        return
    _set_state(context, user_id, state="awaiting_search")
    await _dm_prompt(query, context, f"{_t('search_title', lang)}\n\n{_t('enter_search', lang)}", lang)


async def _process_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    lang = _get_user_lang(user_id)
    keyword = update.message.text.strip().lower()
    data = _load_data()
    results = [t for t in data["tasks"] if keyword in t["content"].lower() or keyword in t["assignee"].lower()]
    _clear_state(context, user_id)
    if not results:
        await update.message.reply_text(_t("search_empty", lang), reply_markup=_main_menu_kb(user_id, lang))
        return
    lines = [f"{_t('search_title', lang)} — \"{keyword}\" ({len(results)})\n"]
    for t in results:
        lines += [_format_task_card(t, data["users"], lang), ""]
    text = "\n".join(lines)
    if len(text) > 4000:
        text = text[:4000] + "\n..."
    await update.message.reply_text(text, reply_markup=_main_menu_kb(user_id, lang))


# ──────────────────────────────────────────
# 📊 월간 통계 (CEO 전용)
# ──────────────────────────────────────────

async def cb_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await _dm(query, context, _t("report_only", lang), _back_kb(lang))
        return
    data = _load_data()
    now = datetime.now(KST)
    month_start = now.replace(day=1).strftime("%Y-%m-%d")
    monthly = [t for t in data["tasks"] if t.get("created_at", "") >= month_start]
    if not monthly:
        await _dm(query, context, _t("no_tasks", lang), _back_kb(lang))
        return
    total = len(monthly)
    comp = len([t for t in monthly if t["status"] == "완료"])
    prog = len([t for t in monthly if t["status"] == "진행중"])
    pend = len([t for t in monthly if t["status"] == "대기"])
    over = len([t for t in monthly if t["status"] == "지연"])
    rate = round(comp / total * 100) if total else 0
    lines = [
        f"{_t('monthly_title', lang)}", f"Date: {now.strftime('%Y.%m')}\n",
        f"Total: {total}",
        f"  {_t('st_done', lang)}: {comp} ({rate}%)",
        f"  {_t('st_progress', lang)}: {prog}",
        f"  {_t('st_overdue', lang)}: {over}",
        f"  {_t('st_pending', lang)}: {pend}", "",
    ]
    # 담당자별
    stats = {}
    for t in monthly:
        n = t["assignee"]
        if n not in stats:
            stats[n] = {"done": 0, "overdue": 0, "total": 0}
        stats[n]["total"] += 1
        if t["status"] == "완료":
            stats[n]["done"] += 1
        elif t["status"] == "지연":
            stats[n]["overdue"] += 1
    for n, s in stats.items():
        lines.append(f"  @{n} — {s['done']} done / {s['overdue']} overdue / {s['total']} total")
    await _dm(query, context, "\n".join(lines), _back_kb(lang))


# ──────────────────────────────────────────
# 📈 보고서 (DM, CEO 전용)
# ──────────────────────────────────────────

async def cb_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    lang = _get_user_lang(user_id)
    if not _is_admin(user_id):
        await _dm(query, context, _t("report_only", lang), _back_kb(lang))
        return
    data = _load_data()
    tasks = data["tasks"]
    if not tasks:
        await _dm(query, context, _t("no_tasks", lang), _back_kb(lang))
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

    await _dm(query, context, "\n".join(lines), _back_kb(lang))


# ──────────────────────────────────────────
# 텍스트 입력 라우터
# ──────────────────────────────────────────

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    # 메모리에 상태 없으면 파일에서 복원 (서버 재시작 대비)
    _restore_state(context, user_id)
    state = context.user_data.get("state")
    if not state:
        return
    print(f"[text-input] user={user_id} state={state} text='{(update.message.text or '')[:30]}'", flush=True)
    if state == "awaiting_task_assignee":
        await _process_task_assignee_custom(update, context)
    elif state == "awaiting_task_content":
        await _process_task_content(update, context)
    elif state == "awaiting_task_deadline":
        await _process_task_deadline_custom(update, context)
    elif state == "awaiting_progress":
        await _process_progress_update(update, context)
    elif state == "awaiting_edit_content":
        await _process_edit_content(update, context)
    elif state == "awaiting_edit_deadline":
        await _process_edit_deadline(update, context)
    elif state == "awaiting_search":
        await _process_search(update, context)


# ──────────────────────────────────────────
# 그룹챗 자동 감지
# ──────────────────────────────────────────

async def _track_group_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type in ("group", "supergroup"):
        _save_group_chat_id(update.effective_chat.id)
    if update.effective_user and not update.effective_user.is_bot:
        _track_user(update.effective_user)


# ──────────────────────────────────────────
# 스케줄 Job — 마감일 알림 (매일 9시 KST, 그룹 공개)
# ──────────────────────────────────────────

async def _daily_deadline_reminder(context: ContextTypes.DEFAULT_TYPE):
    group_ids = _get_group_chat_ids()
    if not group_ids:
        return
    data = _load_data()
    today = datetime.now(KST).date()
    overdue, due_today, due_tomorrow, auto_overdue = [], [], [], []
    changed = False
    for t in data["tasks"]:
        if t["status"] in ("완료", "취소", "지연"):
            continue
        try:
            dl = datetime.strptime(t["deadline"], "%Y.%m.%d").date()
        except ValueError:
            continue
        d = (dl - today).days
        if d <= -3:
            # 3일 이상 지연 → 자동 지연 처리
            t["status"] = "지연"
            auto_overdue.append(t)
            changed = True
        elif d < 0:
            overdue.append(t)
        elif d == 0:
            due_today.append(t)
        elif d == 1:
            due_tomorrow.append(t)
    if changed:
        _save_data(data)
    if not overdue and not due_today and not due_tomorrow and not auto_overdue:
        return
    lines = ["⏰ Deadline Alert\n"]
    if auto_overdue:
        lines.append("🔴 Auto-Overdue (3+ days):")
        for t in auto_overdue:
            lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']}) — {t['deadline']}")
        lines.append("")
        # CEO DM 알림
        if TELEGRAM_ADMIN_ID:
            ceo_lines = ["🔴 지연 자동 처리됨:\n"]
            for t in auto_overdue:
                ceo_lines.append(f"  #{t['id']:03d} {t['content']} (@{t['assignee']})")
            try:
                await context.bot.send_message(chat_id=int(TELEGRAM_ADMIN_ID), text="\n".join(ceo_lines))
            except Exception:
                pass
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
# 스케줄 Job — 주간 보고서 (매주 월 9시 KST, 그룹 공개)
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
    _bot_app.add_handler(CommandHandler("debug", cmd_debug))

    _bot_app.add_handler(CallbackQueryHandler(cb_menu, pattern="^menu$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_help, pattern="^help$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_lang_start, pattern="^lang$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_set_lang, pattern=r"^setlang:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_members_start, pattern="^members$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_member_select, pattern=r"^ma:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_assign_role, pattern=r"^mr:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_start, pattern="^task$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_assignee, pattern=r"^ta:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_deadline, pattern=r"^td:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_task_priority, pattern=r"^tp:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_edit_start, pattern="^edit$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_edit_select, pattern=r"^ed:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_edit_field, pattern=r"^edf:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_reassign_start, pattern="^reassign$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_reassign_select, pattern=r"^ra:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_reassign_member, pattern=r"^rm:"))
    _bot_app.add_handler(CallbackQueryHandler(cb_search_start, pattern="^search$"))
    _bot_app.add_handler(CallbackQueryHandler(cb_monthly, pattern="^monthly$"))
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
