from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.user_state import user_data
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, place_keyboard
from db.supabase_client import TIME_MAP, ENERGY_MAP, PLACE_MAP
from db.supabase_client import supabase

from utils.amplitude_logger import log_event

update_filters_router = Router()


@update_filters_router.message(Command("update_filters"))
@update_filters_router.callback_query(F.data == "update_filters")
async def show_update_options(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    filters = user_data.get(user_id)
    if not filters:
        # Пробуем достать фильтры из Supabase
        response = supabase.table("user_filters").select("*").eq(
            "user_id", user_id).execute()
        if not response.data:
            text = "Сначала пройдите подбор: /start"
            if isinstance(event, types.CallbackQuery):
                await event.message.answer(text)
                await event.answer()
            else:
                await event.answer(text)
            return
        filters = response.data[0]
        user_data[user_id] = filters  # 💾 Сохраняем в память

    # ✅ Логирование события
    try:
        log_event(user_id=user_id,
                  event_name="update_filters",
                  event_properties={
                      "age": filters.get("age"),
                      "time": filters.get("time"),
                      "energy": filters.get("energy"),
                      "location": filters.get("location")
                  },
                  session_id=filters.get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log update_filters: {e}")

    time_label = TIME_MAP.get(filters["time"], filters["time"])
    energy_label = ENERGY_MAP.get(filters["energy"], filters["energy"])
    place_label = PLACE_MAP.get(filters["location"], filters["location"])

    text = (f"Ваш текущий выбор:\n"
            f"👶 Возраст: {filters['age']} лет\n"
            f"⏳ Время: {time_label}\n"
            f"⚡️ Энергия: {energy_label}\n"
            f"📍 Место: {place_label}\n\n"
            f"Хотите что-то поменять?")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="Возраст",
                                 callback_data="update_age")
        ],
                         [
                             InlineKeyboardButton(text="Время на игру",
                                                  callback_data="update_time")
                         ],
                         [
                             InlineKeyboardButton(
                                 text="Уровень энергии",
                                 callback_data="update_energy")
                         ],
                         [
                             InlineKeyboardButton(text="Место",
                                                  callback_data="update_place")
                         ]])

    if isinstance(event, types.CallbackQuery):
        await event.message.answer(text, reply_markup=keyboard)
        await event.answer()
    else:
        await event.answer(text, reply_markup=keyboard)


@update_filters_router.callback_query(F.data == "update_age")
async def update_age(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["mode"] = "update"
    await callback.message.answer("Выберите новый возраст:",
                                  reply_markup=age_keyboard)
    await callback.answer()


@update_filters_router.callback_query(F.data == "update_time")
async def update_time(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["mode"] = "update"
    await callback.message.answer("Сколько у вас есть времени на игру?",
                                  reply_markup=time_keyboard)
    await callback.answer()


@update_filters_router.callback_query(F.data == "update_energy")
async def update_energy(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["mode"] = "update"
    await callback.message.answer("Сколько у вас энергии на игру?",
                                  reply_markup=energy_keyboard)
    await callback.answer()


@update_filters_router.callback_query(F.data == "update_place")
async def update_place(callback: types.CallbackQuery):
    user_data[callback.from_user.id]["mode"] = "update"
    await callback.message.answer("Где будете играть?",
                                  reply_markup=place_keyboard)
    await callback.answer()
