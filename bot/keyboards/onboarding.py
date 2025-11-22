from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

age_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="3–4 года", callback_data="age_3_4"),
        InlineKeyboardButton(text="5–6 лет", callback_data="age_5_6"),
    ],
    [
        InlineKeyboardButton(text="7–8 лет", callback_data="age_7_8"),
        InlineKeyboardButton(text="9–10+ лет", callback_data="age_9_10"),
    ],
])

time_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="15 мин", callback_data="time_15"),
        InlineKeyboardButton(text="30 мин", callback_data="time_30"),
    ],
    [
        InlineKeyboardButton(text="1 час", callback_data="time_60"),
        InlineKeyboardButton(text="Более часа", callback_data="time_more"),
    ]
])

energy_keyboard = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="Хочу спокойно пообщаться",
                             callback_data="energy_low")
    ],
    [
        InlineKeyboardButton(
            text="Немного бодрый — готов на лёгкую активность",
            callback_data="energy_mid")
    ],
    [
        InlineKeyboardButton(text="Полон сил!",
                             callback_data="energy_high")
    ],
])

location_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Дома", callback_data="location_home"),
    InlineKeyboardButton(text="На улице", callback_data="location_outside"),
]])

# клавиатура под L0 карточкой
activity_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Играем ▶️",
                         callback_data="activity_details")
], [
    InlineKeyboardButton(text="Следующую ⏩️", callback_data="activity_next")
]])

# клавиатура под L1 карточкой
activity_l1_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Следующую ⏩️", callback_data="activity_next")
]])
