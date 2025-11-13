from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.amplitude_logger import log_event
from handlers.start import user_data

subscribe_router = Router()

@subscribe_router.message(Command("subscribe"))
async def subscribe(message: types.Message):
    user_id = message.from_user.id
    session_id = user_data.get(user_id, {}).get("session_id")

    log_event(user_id=user_id, event_name="subscribe_to_channel", session_id=session_id)

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔔 Подписаться на канал", url="https://t.me/blizkie_igry")
    ]])
    await message.answer("Подпишись, чтобы не пропустить новые идеи 💛", reply_markup=kb)

# fallback на сырой текст
@subscribe_router.message(F.text == "/subscribe")
async def subscribe_text(message: types.Message):
    await subscribe(message)
