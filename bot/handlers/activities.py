from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from db.supabase_client import get_activity, supabase, TIME_MAP, ENERGY_MAP, PLACE_MAP
from utils.amplitude_logger import log_event
from .user_state import user_data

activities_router = Router()


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

    log_event(user_id=callback.from_user.id,
              event_name="show_activity_L0",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["place"]
              },
              session_id=user_data.get(callback.from_user.id,
                                       {}).get("session_id"))

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)


@activities_router.callback_query(F.data.startswith("activity_details:"))
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

    log_event(user_id=callback.from_user.id,
              event_name="show_activity_L1",
              event_properties={
                  "activity_id": activity_id,
                  "age": activity.get("age_min"),
                  "time": activity.get("time_required"),
                  "energy": activity.get("energy"),
                  "location": activity.get("location")
              },
              session_id=user_data.get(callback.from_user.id,
                                       {}).get("session_id"))

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()


@activities_router.callback_query(F.data == "activity_next")
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

    log_event(user_id=callback.from_user.id,
              event_name="show_activity_L0",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["place"]
              },
              session_id=user_data.get(callback.from_user.id,
                                       {}).get("session_id"))

    log_event(user_id=callback.from_user.id,
              event_name="show_next_activity",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["place"]
              },
              session_id=user_data.get(callback.from_user.id,
                                       {}).get("session_id"))

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()


@activities_router.message(Command("next"))
async def next_command_handler(message: types.Message):
    user_id = message.from_user.id
    filters = user_data.get(user_id)

    if not filters:
        await message.answer("Сначала пройдите подбор заново: /start")
        return

    activity = get_activity(age=int(filters["age"]),
                            time_required=TIME_MAP[filters["time"]],
                            energy=ENERGY_MAP[filters["energy"]],
                            location=PLACE_MAP[filters["place"]])

    if not activity:
        await message.answer("😔 Больше идей нет для этих условий.")
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Расскажи как играть",
                              callback_data=f"activity_details:{activity['id']}")],
        [InlineKeyboardButton(text="Покажи еще идею",
                              callback_data="activity_next")],
        [InlineKeyboardButton(text="Хочу другие советы",
                              callback_data="update_filters")]
    ])

    await message.answer_photo(photo=activity["image_url"],
                               caption=text,
                               parse_mode="Markdown",
                               reply_markup=keyboard)

    log_event(user_id=user_id,
              event_name="show_next_activity",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["place"]
              },
              session_id=filters.get("session_id"))