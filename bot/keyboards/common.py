from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

start_inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Начнем!", callback_data="start_onboarding")
]])

favorites_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="❤️ Мои любимые", callback_data="show_favorites")]
])

def favorite_actions_keyboard(activity_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Добавить в любимые ❤️", callback_data=f"add_fav_{activity_id}")],
        [InlineKeyboardButton(text="Удалить из любимых ❌", callback_data=f"remove_fav_{activity_id}")]
    ])