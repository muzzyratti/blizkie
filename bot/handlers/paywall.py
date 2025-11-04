from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.amplitude_logger import log_event

paywall_router = Router()

def paywall_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔓 Открыть всё", callback_data="paywall:open"),
        InlineKeyboardButton(text="🪶 Продолжить L0", callback_data="paywall:continue_l0"),
    ],[
        InlineKeyboardButton(text="Позже", callback_data="paywall:later"),
    ]])

async def send_universal_paywall(msg_or_cb, reason: str, user_id: int, session_id: str|None):
    text = (
        "🧩 Полный доступ к играм\n\n"
        "Вы уже открыли все доступные подробные идеи в бесплатной версии.\n"
        "Откройте полный доступ — 140+ тёплых игр с понятными шагами,\n"
        "сохраняйте любимые и играйте когда удобно."
    )
    log_event(user_id, "paywall_shown", {"reason": reason, "session_id": session_id})
    if isinstance(msg_or_cb, types.CallbackQuery):
        await msg_or_cb.message.answer(text, reply_markup=paywall_kb())
        await msg_or_cb.answer()
    else:
        await msg_or_cb.answer(text, reply_markup=paywall_kb())

@paywall_router.callback_query(F.data.startswith("paywall:"))
async def on_paywall_choice(cb: types.CallbackQuery):
    decision = cb.data.split(":")[1]  # open | continue_l0 | later
    log_event(cb.from_user.id, "paywall_decision", {"decision": decision})
    if decision == "open":
        await cb.message.answer("Скоро подключим оплату. А пока можно листать L0 🙌")
    elif decision == "continue_l0":
        await cb.message.answer("Ок! Продолжаем короткие идеи 🪶")
    else:
        await cb.message.answer("Хорошо, напомню позже.")
    await cb.answer()
