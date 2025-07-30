from aiogram import Router, types
from aiogram.filters import Command
from utils.amplitude_logger import log_event
from handlers.start import user_data

feedback_router = Router()


@feedback_router.message(Command("feedback"))
async def feedback(message: types.Message):
    user_id = message.from_user.id
    session_id = user_data.get(user_id, {}).get("session_id")

    try:
        log_event(user_id=user_id,
                  event_name="feedback_menu",
                  session_id=session_id)
    except Exception as e:
        print(f"[Amplitude] Failed to log feedback_menu: {e}")

    await message.answer(
        "🧸 Если хочешь поделиться отзывом, предложением, задать вопрос или рассказать об ошибке — напиши прямо Саше - создателю бота 💌\n\n"
        "Вот его Telegram: [@discoklopkov](https://t.me/discoklopkov)\n\n"
        "Саша точно прочитает и ответит 🙌",
        parse_mode="Markdown")
