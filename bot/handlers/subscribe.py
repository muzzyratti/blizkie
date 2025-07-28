from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.amplitude_logger import log_event
from handlers.start import user_data

subscribe_router = Router()

@subscribe_router.message(Command("subscribe"))
async def subscribe(message: types.Message):
    user_id = message.from_user.id
    session_id = user_data.get(user_id, {}).get("session_id")

    try:
        log_event(user_id=user_id,
                  event_name="subscribe_to_channel",
                  session_id=session_id)
    except Exception as e:
        print(f"[Amplitude] Failed to log subscribe_to_channel: {e}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔔 Подписаться на канал",
                             url="https://t.me/blizkie_igry")
    ]])
    await message.answer("Подпишись, чтобы не пропустить идеи 💛",
                         reply_markup=keyboard)
