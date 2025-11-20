from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from handlers.user_state import user_data
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, location_keyboard
from db.supabase_client import TIME_MAP, ENERGY_MAP, location_MAP, supabase
from utils.amplitude_logger import log_event
from utils.session import ensure_filters  # ✅ добавлено

update_filters_router = Router()


@update_filters_router.message(Command("update_filters"))
@update_filters_router.callback_query(F.data == "update_filters")
async def show_update_options(event: types.Message | types.CallbackQuery):
    user_id = event.from_user.id
    ctx = ensure_filters(user_id)  # ✅ централизовано

    # ✅ Поддержка старого ключа "time"
    time_value = ctx.get("time_required") or ctx.get("time")
    energy_value = ctx.get("energy")
    location_value = ctx.get("location")
    age_value = ctx.get("age") or f"{ctx.get('age_min', '?')}-{ctx.get('age_max', '?')}"

    # ✅ Логирование события
    try:
        log_event(
            user_id=user_id,
            event_name="update_filters",
            event_properties={
                "age": age_value,
                "time": time_value,
                "energy": energy_value,
                "location": location_value
            },
            session_id=ctx["session_id"]
        )
    except Exception as e:
        print(f"[Amplitude] Failed to log update_filters: {e}")

    # ✅ Безопасное отображение меток
    time_label = TIME_MAP.get(time_value, time_value)
    energy_label = ENERGY_MAP.get(energy_value, energy_value)
    location_label = location_MAP.get(location_value, location_value)

    text = (f"Ваши текущие параметры:\n\n"
            f"👶 Возраст: {age_value} лет\n"
            f"⏳ Время: {time_label}\n"
            f"⚡️ Энергия: {energy_label}\n"
            f"📍 Место: {location_label}\n\n"
            f"Хотите что-то поменять?")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Возраст", callback_data="update_age")],
        [InlineKeyboardButton(text="Время на игру", callback_data="update_time")],
        [InlineKeyboardButton(text="Уровень энергии", callback_data="update_energy")],
        [InlineKeyboardButton(text="Место", callback_data="update_location")]
    ])

    if isinstance(event, types.CallbackQuery):
        await event.message.answer(text, reply_markup=keyboard, disable_web_page_preview=True)
        await event.answer()
    else:
        await event.answer(text, reply_markup=keyboard, disable_web_page_preview=True)


@update_filters_router.callback_query(F.data == "update_age")
async def update_age(callback: types.CallbackQuery):
    ctx = ensure_filters(callback.from_user.id)
    ctx["mode"] = "update"
    await callback.message.answer("Выберите новый возраст:", reply_markup=age_keyboard, disable_web_page_preview=True)
    await callback.answer()


@update_filters_router.callback_query(F.data == "update_time")
async def update_time(callback: types.CallbackQuery):
    ctx = ensure_filters(callback.from_user.id)
    ctx["mode"] = "update"
    await callback.message.answer("Сколько у вас есть времени на игру?", reply_markup=time_keyboard, disable_web_page_preview=True)
    await callback.answer()


@update_filters_router.callback_query(F.data == "update_energy")
async def update_energy(callback: types.CallbackQuery):
    ctx = ensure_filters(callback.from_user.id)
    ctx["mode"] = "update"
    await callback.message.answer("Сколько у вас энергии на игру?", reply_markup=energy_keyboard, disable_web_page_preview=True)
    await callback.answer()


@update_filters_router.callback_query(F.data == "update_location")
async def update_location(callback: types.CallbackQuery):
    ctx = ensure_filters(callback.from_user.id)
    ctx["mode"] = "update"
    await callback.message.answer("Где будете играть?", reply_markup=location_keyboard, disable_web_page_preview=True)
    await callback.answer()
