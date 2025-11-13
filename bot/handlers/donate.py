from aiogram import Router, types, F
from aiogram.filters import Command

donate_router = Router()

@donate_router.message(Command("donate"))
async def donate_command(message: types.Message):
    await message.answer(
        "🙏 Проект делаем с любовью. Если хочешь поддержать — вот ссылка:\n"
        "https://www.donationalerts.com/r/alexklop"
    )

@donate_router.message(F.text == "/donate")
async def donate_text(message: types.Message):
    await donate_command(message)
