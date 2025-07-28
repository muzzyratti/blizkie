from aiogram import Router, types
from aiogram.filters import Command

feedback_router = Router()


@feedback_router.message(Command("feedback"))
async def feedback(message: types.Message):
    await message.answer(
        "🧸 Если хочешь поделиться словом, задать вопрос или рассказать об ошибке — напиши прямо Саше - создателю бота 💌\n\n"
        "Вот его Telegram: [@discoklopkov](https://t.me/discoklopkov)\n\n"
        "Саша точно прочитает и ответит 🙌",
        parse_mode="Markdown")
