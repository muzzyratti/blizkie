from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.amplitude_logger import log_event
from utils.push_scheduler import schedule_paywall_followup
from utils.paywall_guard import l0_views_count, _rules
from config import SUPPORT_USERNAME
from handlers.user_state import user_data

paywall_router = Router()

def paywall_kb(can_continue_l0: bool):
    rows = []
    rows.append([InlineKeyboardButton(text="🔓 Открыть всё", callback_data="subscribe")])
    if can_continue_l0:
        rows.append([InlineKeyboardButton(text="🪶 Продолжить L0", callback_data="activity_next")])
    if SUPPORT_USERNAME:
        rows.append([InlineKeyboardButton(text="💬 Вопрос в поддержку", url=f"https://t.me/{SUPPORT_USERNAME}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def send_universal_paywall(msg_or_cb, reason: str, user_id: int, session_id: str | None):
    text = (
        "🧩 *Полный доступ к играм*\n\n"
        "Вы открыли максимум в бесплатной версии.\n"
        "Подключите полный доступ — 140+ тёплых игр с понятными шагами,\n"
        "сохраняйте любимые и играйте когда удобно."
    )
    log_event(user_id, "paywall_shown", {"reason": reason, "session_id": session_id})
    
    ctx = user_data.setdefault(user_id, {})
    ctx["last_paywall_reason"] = reason

    rules = _rules() or {"l0": 15}
    can_continue = l0_views_count(user_id) < rules["l0"]

    kb = paywall_kb(can_continue)
    if isinstance(msg_or_cb, types.CallbackQuery):
        await msg_or_cb.message.answer(text, reply_markup=kb, parse_mode="Markdown")
        await msg_or_cb.answer()
    else:
        await msg_or_cb.answer(text, reply_markup=kb, parse_mode="Markdown")

@paywall_router.callback_query(F.data.startswith("paywall:"))
async def on_legacy_paywall_choice(cb: types.CallbackQuery):
    # на случай старых callback_data — не ломаем совместимость
    log_event(cb.from_user.id, "paywall_decision", {"decision": cb.data})
    await cb.message.answer("Ок! Продолжаем.", disable_web_page_preview=True)
    await cb.answer()
