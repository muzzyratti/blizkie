from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.common import start_inline_keyboard
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, place_keyboard
from db.supabase_client import get_activity, supabase, ENERGY_MAP, TIME_MAP, PLACE_MAP
from utils.amplitude_logger import log_event, set_user_properties
from uuid import uuid4

router = Router()
user_data = {}


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    log_event(user_id=message.from_user.id,
              event_name="start_bot",
              event_properties={"source": "telegram"})

    text = ("Привет, я бот *Близкие Игры*! 🤗\n\n"
            "Помогаю находить идеи, как провести время с детьми так, "
            "чтобы всем было тепло, весело и немного волшебно ✨")
    await message.answer(text,
                         parse_mode="Markdown",
                         reply_markup=start_inline_keyboard)


@router.callback_query(F.data == "start_onboarding")
async def start_onboarding(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    user_data[user_id] = {"mode": "onboarding"}

    log_event(user_id, "onboarding_started")

    await callback.message.answer(
        "Сколько лет вашему ребёнку? (если их несколько, выбирайте младшего):",
        reply_markup=age_keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("age_"))
async def process_age(callback: types.CallbackQuery):
    age = int(callback.data.split("_")[1])
    user_id = callback.from_user.id
    user_data.setdefault(user_id, {})["age"] = age

    log_event(user_id, "set_age", {"age": age})
    set_user_properties(user_id, {"age": age})

    mode = user_data[user_id].get("mode")
    if mode == "onboarding":
        await callback.message.answer(
            f"Вы выбрали возраст ребёнка: {age} лет.\n\n"
            "Сколько у вас есть времени на активность?",
            reply_markup=time_keyboard)
    elif mode == "update":
        await callback.message.answer("Возраст обновлён. Вот идея для вас 👇")
        await show_next_activity(callback)

    await callback.answer()


@router.callback_query(F.data.startswith("time_"))
async def process_time(callback: types.CallbackQuery):
    time_choice = callback.data.split("_")[1]
    user_id = callback.from_user.id
    user_data[user_id]["time"] = time_choice

    log_event(user_id, "set_time", {"time": time_choice})
    set_user_properties(user_id, {"time": time_choice})

    mode = user_data[user_id].get("mode")
    if mode == "onboarding":
        await callback.message.answer(
            "Сколько у вас сегодня энергии на игру? (честно 😌)",
            reply_markup=energy_keyboard)
    elif mode == "update":
        await callback.message.answer("Время обновлено. Вот идея для вас 👇")
        await show_next_activity(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("energy_"))
async def process_energy(callback: types.CallbackQuery):
    energy_choice = callback.data.split("_")[1]
    user_id = callback.from_user.id
    user_data[user_id]["energy"] = energy_choice

    log_event(user_id, "set_energy", {"energy": energy_choice})
    set_user_properties(user_id, {"energy": energy_choice})

    mode = user_data[user_id].get("mode")
    if mode == "onboarding":
        await callback.message.answer("Где будете проводить время?",
                                      reply_markup=place_keyboard)
    elif mode == "update":
        await callback.message.answer("Энергия обновлена. Вот идея для вас 👇")
        await show_next_activity(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("place_"))
async def process_place(callback: types.CallbackQuery):
    place_choice = callback.data.split("_")[1]
    user_id = callback.from_user.id
    user_data[user_id]["place"] = place_choice

    log_event(user_id, "set_place", {"place": place_choice})
    set_user_properties(user_id, {"place": place_choice})

    mode = user_data[user_id].get("mode")
    if mode == "onboarding":
        log_event(user_id, "onboarding_completed")
        await send_activity(callback)
    elif mode == "update":
        await callback.message.answer("Место обновлено. Вот идея для вас 👇")
        await show_next_activity(callback)
    await callback.answer()


async def send_activity(callback: types.CallbackQuery):
    filters = user_data[callback.from_user.id]
    activity = get_activity(age=int(filters["age"]),
                            time_required=TIME_MAP[filters["time"]],
                            energy=ENERGY_MAP[filters["energy"]],
                            location=PLACE_MAP[filters["place"]])

    if not activity:
        await callback.message.answer(
            "😔 Нет идей для таких условий, попробуйте изменить фильтры.")
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Расскажи как играть",
                callback_data=f"activity_details:{activity['id']}")
        ],
        [
            InlineKeyboardButton(text="Покажи еще идею",
                                 callback_data="activity_next")
        ],
        [
            InlineKeyboardButton(text="Хочу другие советы",
                                 callback_data="update_filters")
        ]
    ])

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)


@router.callback_query(F.data.startswith("activity_details:"))
async def show_activity_details(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    activity_id = int(callback.data.split(":")[1])

    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if not response.data:
        await callback.message.answer(
            "😔 Не удалось найти подробности активности.")
        await callback.answer()
        return

    activity = response.data[0]

    fav_response = supabase.table("favorites") \
        .select("id") \
        .eq("user_id", user_id) \
        .eq("activity_id", activity_id) \
        .execute()

    is_favorite = len(fav_response.data) > 0

    summary = "\n".join([f"💡 {s}" for s in (activity['summary'] or [])])
    text = (
        f"🎲 *{activity['title']}*\n\n"
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}")

    row1 = []
    if is_favorite:
        row1.append(
            InlineKeyboardButton(text="Убрать из любимых ✖️",
                                 callback_data=f"remove_fav:{activity_id}"))
    else:
        row1.append(
            InlineKeyboardButton(text="Добавить в любимые ❤️",
                                 callback_data=f"favorite_add:{activity_id}"))

    row1.append(
        InlineKeyboardButton(text="Покажи еще идею",
                             callback_data="activity_next"))

    row2 = [
        InlineKeyboardButton(text="Хочу другие советы",
                             callback_data="update_filters"),
        InlineKeyboardButton(text="Поделиться идеей 💌",
                             callback_data=f"share_activity:{activity_id}")
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[row1, row2])

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "activity_next")
async def show_next_activity(callback: types.CallbackQuery):
    filters = user_data.get(callback.from_user.id)
    if not filters:
        await callback.message.answer("Сначала пройдите подбор заново: /start")
        await callback.answer()
        return

    activity = get_activity(age=int(filters["age"]),
                            time_required=TIME_MAP[filters["time"]],
                            energy=ENERGY_MAP[filters["energy"]],
                            location=PLACE_MAP[filters["place"]])

    if not activity:
        await callback.message.answer("😔 Больше идей нет для этих условий.")
        await callback.answer()
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Расскажи как играть",
                callback_data=f"activity_details:{activity['id']}")
        ],
        [
            InlineKeyboardButton(text="Покажи еще идею",
                                 callback_data="activity_next")
        ],
        [
            InlineKeyboardButton(text="Хочу другие советы",
                                 callback_data="update_filters")
        ]
    ])

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()
