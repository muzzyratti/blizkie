from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.onboarding import age_keyboard
from keyboards.common import start_inline_keyboard
from db.supabase_client import TIME_MAP, ENERGY_MAP, PLACE_MAP
from utils.amplitude_logger import log_event
from db.user_sessions import load_user_session
from handlers.user_state import user_data
from uuid import uuid4

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id

    # Загружаем сохранённую сессию, если есть
    session = load_user_session(user_id)
    if session:
        user_data[user_id] = {
            "age": session["age"],
            "time": session["time"],
            "energy": session["energy"],
            "place": session["place"],
            "session_id": session.get("session_id")
        }

    filters = user_data.get(user_id)

    log_event(user_id=user_id,
              event_name="start_bot",
              event_properties={"source": "telegram"})

    if filters:
        # Маппинг по-человечески
        time_label = TIME_MAP.get(filters["time"], filters["time"])
        energy_label = ENERGY_MAP.get(filters["energy"], filters["energy"])
        place_label = PLACE_MAP.get(filters["place"], filters["place"])

        text = (
            "👋 Привет! У нас уже есть твой выбор:\n\n"
            f"👶 Возраст: {filters['age']} лет\n"
            f"⏳ Время: {time_label}\n"
            f"⚡️ Энергия: {energy_label}\n"
            f"📍 Место: {place_label}\n\n"
            "Что будем делать?")
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Показать идею", callback_data="start_with_saved")],
                [InlineKeyboardButton(text="Пройти подбор заново", callback_data="start_onboarding")]
            ])
        await message.answer(text, reply_markup=keyboard)
    else:
        text = ("Привет, я бот *Близкие Игры*! 🤗\n\n"
                "Помогаю находить идеи, как провести время с детьми так, "
                "чтобы всем было тепло, весело и немного волшебно ✨")
        await message.answer(text,
                             parse_mode="Markdown",
                             reply_markup=start_inline_keyboard)

@router.callback_query(F.data == "start_onboarding")
async def start_onboarding(callback: types.CallbackQuery):
    user_data[callback.from_user.id] = {"mode": "onboarding", "session_id": str(uuid4())}
    await callback.message.answer("Сколько лет вашему ребёнку?", reply_markup=age_keyboard)
    await callback.answer()

@router.callback_query(F.data == "start_with_saved")
async def start_with_saved(callback: types.CallbackQuery):
    from handlers.activities import show_next_activity
    await show_next_activity(callback)
