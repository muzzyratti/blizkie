from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(Command("donate"))
async def donate_command(message: types.Message):
    await message.answer(
        "Проект создаётся с любовью и энтузиазмом, чтобы дарить вам тёплые моменты с детьми. 💛\n\n"
        "Если хочется поддержать — вот ссылка на тёплый жест:\n"
        "https://www.donationalerts.com/r/alexklop"
    )