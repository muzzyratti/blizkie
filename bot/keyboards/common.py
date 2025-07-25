from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

start_inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Начнем!", callback_data="start_onboarding")
]])
