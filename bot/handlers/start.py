from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.common import start_inline_keyboard
from db.supabase_client import supabase, ENERGY_MAP, TIME_MAP, location_MAP
from utils.session import ensure_filters
from utils.amplitude_logger import log_event
from handlers.user_state import user_data

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id

    # создаём/обновляем контекст пользователя
    ctx = ensure_filters(user_id)

    # при новом /start — всегда новая сессия
    from uuid import uuid4
    from datetime import datetime
    ctx["session_id"] = f"{user_id}_{datetime.now().strftime('%Y%m%d')}_{uuid4().hex[:6]}"
    ctx["created_at"] = datetime.utcnow()
    ctx["actions_count"] = 0
    ctx["first_event"] = "start_bot"
    ctx["last_event"] = "start_bot"
    ctx["source"] = "telegram"
    ctx["device_info"] = {
        "language": message.from_user.language_code,
        "is_premium": getattr(message.from_user, "is_premium", False),
    }

    # логируем старт
    log_event(
        user_id=user_id,
        event_name="start_bot",
        event_properties={"source": "telegram"},
        session_id=ctx["session_id"],
    )

    # проверяем, есть ли сохранённые фильтры
    response = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
    filters = response.data[0] if response.data else None

    if filters:
        # Формируем текст с текущими фильтрами
        time_label = TIME_MAP.get(filters.get("time_required"), filters.get("time_required", "не указано"))
        energy_label = ENERGY_MAP.get(filters.get("energy"), filters.get("energy", "не указана"))
        location_label = location_MAP.get(filters.get("location"), filters.get("location", "не указано"))
        age_label = f"{filters.get('age_min', '?')}-{filters.get('age_max', '?')}"

        text = (
            "Привет! ✨\n\n"
            "Ваши текущие фильтры:\n"
            f"👶 Возраст: {age_label} лет\n"
            f"⏳ Время: {time_label}\n"
            f"⚡️ Энергия: {energy_label}\n"
            f"📍 Место: {location_label}\n\n"
            "Хотите продолжить с этими фильтрами или выбрать заново?"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Хочу новые фильтры", callback_data="start_onboarding")],
                [InlineKeyboardButton(text="▶️ Продолжить с этими", callback_data="continue_with_filters")],
            ]
        )

        await message.answer(text, reply_markup=keyboard)

    else:
        # Стартовое приветствие, если пользователь впервые
        text = (
            "Привет, я бот *Близкие Игры*! 🤗\n\n"
            "Помогаю находить идеи, как провести время с детьми так, "
            "чтобы всем было тепло, весело и немного волшебно ✨"
        )

        await message.answer(text, parse_mode="Markdown", reply_markup=start_inline_keyboard)
