from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db.user_sessions import save_user_session, load_user_session
from utils.amplitude_logger import log_event
from handlers.user_state import user_data

subscribe_router = Router()

CHANNEL_USERNAME = "blizkie_igry"


@subscribe_router.message(Command("subscribe"))
async def subscribe(message: types.Message):
    user_id = message.from_user.id
    session_id = user_data.get(user_id, {}).get("session_id")

    log_event(user_id=user_id,
              event_name="subscribe_prompt",
              session_id=session_id)

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="🔔 Подписаться на канал",
                                 url="https://t.me/blizkie_igry")
        ],
                         [
                             InlineKeyboardButton(
                                 text="✅ Я подписался",
                                 callback_data="check_subscription")
                         ]])
    await message.answer("Подпишись, чтобы не пропустить новые идеи 💛",
                         reply_markup=keyboard)


@subscribe_router.callback_query(F.data == "check_subscription")
async def check_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    session = load_user_session(user_id) or {}

    user_data[user_id]["subscribed_to_channel"] = True
    save_user_session(user_id, user_data[user_id])

    try:
        member = await callback.bot.get_chat_member(
            chat_id=f"@{CHANNEL_USERNAME}", user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            session["subscribed_to_channel"] = True
            save_user_session(user_id, session)
            user_data[user_id] = session
            log_event(user_id=user_id, event_name="subscribed_success")
            await callback.message.answer("Спасибо, что подписался! ❤️")
        else:
            await callback.message.answer("Кажется, ты ещё не подписан 🤔")
    except Exception as e:
        print(f"[TG] Error checking subscription: {e}")
        await callback.message.answer(
            "Не получилось проверить подписку. Попробуй позже.")
    await callback.answer()
