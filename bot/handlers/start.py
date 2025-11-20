from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from keyboards.common import start_inline_keyboard
from db.supabase_client import supabase, ENERGY_MAP, TIME_MAP, location_MAP
from utils.session import ensure_filters
from utils.amplitude_logger import log_event
from handlers.user_state import user_data

router = Router()

PHOTO_URL = "https://hcfnytsjrqtwstyivnrx.supabase.co/storage/v1/object/public/push_assets/photo_2025-11-20%2012.06.14.jpeg"


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id

    # создаём/обновляем контекст
    ctx = ensure_filters(user_id)

    # новая сессия
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

    # event
    log_event(
        user_id=user_id,
        event_name="start_bot",
        event_properties={"source": "telegram"},
        session_id=ctx["session_id"],
    )

    # проверяем фильтры
    response = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
    filters = response.data[0] if response.data else None

    # ============================================================
    # 1) Если есть сохранённые фильтры
    # ============================================================
    if filters:
        time_label = TIME_MAP.get(filters.get("time_required"), filters.get("time_required", "не указано"))
        energy_label = ENERGY_MAP.get(filters.get("energy"), filters.get("energy", "не указана"))
        location_label = location_MAP.get(filters.get("location"), filters.get("location", "не указано"))
        age_label = f"{filters.get('age_min', '?')}-{filters.get('age_max', '?')}"

        text = (
            "С возвращением 👋\n\n"
            "Я помню, что тебе было удобно. Вот твои последние параметры:\n\n"
            f"👶 Возраст: *{age_label}* лет\n"
            f"⏳ Время: *{time_label}*\n"
            f"⚡️ Энергия: *{energy_label}*\n"
            f"📍 Место: *{location_label}*\n\n"
            "Хочешь продолжить с ними или подобрать всё заново? ✨"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Подобрать всё заново", callback_data="start_onboarding")],
                [InlineKeyboardButton(text="▶️ Продолжить", callback_data="continue_with_filters")],
            ]
        )

        await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)
        return
        
    await message.answer_photo(
        photo=PHOTO_URL,
        caption=(
            "Привет! Это Саша, создатель «Близких игр» 👋\n\n"
            "Я папа двойняшек. И хорошо знаю момент, когда после работы хочется просто лечь… "
            "но где-то внутри звучит: «Проведи с детьми хотя бы 20–30 минут». А фантазии — ноль.\n\n"
            "Поэтому я сделал этого бота. Он <strong>помогает быстро придумать, что поделать с ребёнком "
            "прямо сейчас</strong> — учитывая возраст, время и даже твой уровень сил.\n\n"
            "Хочется, чтобы дома были не только «ужин–уроки–сон», "
            "а ещё тепло, смех и немного волшебства — то, ради чего мы вообще стараемся ❤️\n\n"
            "Подберём твою первую идею? ✨"
        ),
        parse_mode="HTML",
        reply_markup=start_inline_keyboard  # ← КНОПКА ЗДЕСЬ
    )