from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

subscribe_router = Router()


@subscribe_router.message(Command("subscribe"))
async def subscribe(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔔 Подписаться на канал",
                             url="https://t.me/blizkie_igry")
    ]])
    await message.answer("Подпишись, чтобы не пропустить идеи 💛",
                         reply_markup=keyboard)
