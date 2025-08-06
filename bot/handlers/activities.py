from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandObject
from db.supabase_client import get_activity, supabase, TIME_MAP, ENERGY_MAP, location_MAP
from utils.amplitude_logger import log_event
from .user_state import user_data
import os
from db.seen import get_next_activity_with_filters
from datetime import datetime

activities_router = Router()


def get_activity_by_id(activity_id: int):
    response = supabase.table("activities").select("*").eq(
        "id", activity_id).single().execute()
    return response.data


async def send_activity(callback: types.CallbackQuery):
    filters = user_data[callback.from_user.id]
    activity_id, was_reset = get_next_activity_with_filters(
        user_id=callback.from_user.id,
        age=int(filters["age"]),
        time=filters["time"],
        energy=filters["energy"],
        location=filters["location"])

    if activity_id is None:
        await callback.message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.")
        return
    
    activity = get_activity_by_id(activity_id)

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
            InlineKeyboardButton(text="Хочу другие фильтры",
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
                  "location": filters["location"]
              },
              session_id=user_data.get(callback.from_user.id,
                                       {}).get("session_id"))

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)

    # Записываем просмотр
    supabase.table("seen_activities").upsert({
        "user_id":
        callback.from_user.id,
        "activity_id":
        activity["id"],
        "age":
        filters["age"],
        "time":
        filters["time"],
        "energy":
        filters["energy"],
        "location":
        filters["location"],
        "seen_at":
        datetime.now().isoformat()
    }).execute()


@activities_router.callback_query(F.data.startswith("activity_details:"))
async def show_activity_details(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    activity_id = int(callback.data.split(":")[1])

    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    if not response.data:
        await callback.message.answer("😔 Не удалось найти подробности активности.")
        await callback.answer()
        return

    activity = response.data[0]

    fav_response = supabase.table("favorites") \
        .select("id") \
        .eq("user_id", user_id) \
        .eq("activity_id", activity_id) \
        .execute()

    is_favorite = len(fav_response.data) > 0

    summary = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])

    caption = f"🎲 *{activity['title']}*"
    text = (
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Добавить в любимые ❤️"
                if not is_favorite else "Убрать из любимых ✖️",
                callback_data=f"{'favorite_add' if not is_favorite else 'remove_fav'}:{activity_id}"
            )
        ],
        [
            InlineKeyboardButton(text="Покажи еще идею", callback_data="activity_next")
        ],
        [
            InlineKeyboardButton(text="Хочу другие фильтры", callback_data="update_filters")
        ],
        [
            InlineKeyboardButton(text="Поделиться идеей 💌", callback_data=f"share_activity:{activity_id}")
        ]
    ])

    try:
        if len(caption) + len(text) <= 1024:
            await callback.message.answer_photo(
                photo=activity["image_url"],
                caption=f"{caption}\n\n{text}",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        else:
            await callback.message.answer_photo(
                photo=activity["image_url"],
                caption=caption[:1024],
                parse_mode="Markdown"
            )
            await callback.message.answer(
                text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
    except Exception as e:
        await callback.message.answer("⚠️ Не удалось отобразить идею.")
        print("Ошибка при отправке подробностей:", e)

    log_event(user_id=callback.from_user.id,
              event_name="show_activity_L1",
              event_properties={
                  "activity_id": activity_id,
                  "age": activity.get("age_min"),
                  "time": activity.get("time_required"),
                  "energy": activity.get("energy"),
                  "location": activity.get("location")
              },
              session_id=user_data.get(callback.from_user.id, {}).get("session_id"))

    await callback.answer()


@activities_router.callback_query(F.data == "activity_next")
async def show_next_activity(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    filters = user_data.get(user_id)

    # ✅ Если фильтров нет в памяти — достаём из Supabase
    if not filters:
        response = supabase.table("user_filters").select("*").eq(
            "user_id", user_id).execute()
        if not response.data:
            await callback.message.answer(
                "Сначала пройдите подбор заново: /start")
            await callback.answer()
            return

        filters = response.data[0]
        user_data[user_id] = filters  # 💾 Сохраняем в память для следующих запросов

    activity_id, was_reset = get_next_activity_with_filters(
        user_id=user_id,
        age=int(filters["age"]),
        time=filters["time"],
        energy=filters["energy"],
        location=filters["location"])

    if activity_id is None:
        await callback.message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.")
        return
    
    activity = get_activity_by_id(activity_id)

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
            InlineKeyboardButton(text="Хочу другие фильтры",
                                 callback_data="update_filters")
        ]
    ])

    # ✅ Логирование
    log_event(user_id=user_id,
              event_name="show_activity_L0",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["location"]
              },
              session_id=filters.get("session_id"))

    log_event(user_id=user_id,
              event_name="show_next_activity",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["location"]
              },
              session_id=filters.get("session_id"))

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)

    supabase.table("seen_activities").upsert({
        "user_id":
        user_id,
        "activity_id":
        activity["id"],
        "age":
        filters["age"],
        "time":
        filters["time"],
        "energy":
        filters["energy"],
        "location":
        filters["location"],
        "seen_at":
        datetime.now().isoformat()
    }).execute()

    await callback.answer()


@activities_router.message(Command("next"))
async def next_command_handler(message: types.Message):
    user_id = message.from_user.id
    filters = user_data.get(user_id)

    if not filters:
        response = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
        if not response.data:
            await message.answer("Сначала пройдите подбор заново: /start")
            return

        filters = response.data[0]
        user_data[user_id] = filters  # 💾 Сохраняем в память

    activity_id, was_reset = get_next_activity_with_filters(
        user_id=user_id,
        age=int(filters["age"]),
        time=filters["time"],
        energy=filters["energy"],
        location=filters["location"])

    if activity_id is None:
        await callback.message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.")
        return
    
    activity = get_activity_by_id(activity_id)

    if not activity:
        await message.answer("😔 Больше идей нет для этих условий.")
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
            InlineKeyboardButton(text="Хочу другие фильтры",
                                 callback_data="update_filters")
        ]
    ])

    await message.answer_photo(photo=activity["image_url"],
                               caption=text,
                               parse_mode="Markdown",
                               reply_markup=keyboard)

    supabase.table("seen_activities").upsert({
        "user_id":
        user_id,
        "activity_id":
        activity["id"],
        "age":
        filters["age"],
        "time":
        filters["time"],
        "energy":
        filters["energy"],
        "location":
        filters["location"],
        "seen_at":
        datetime.now().isoformat()
    }).execute()

    log_event(user_id=user_id,
              event_name="show_next_activity",
              event_properties={
                  "activity_id": activity["id"],
                  "age": filters["age"],
                  "time": filters["time"],
                  "energy": filters["energy"],
                  "location": filters["location"]
              },
              session_id=filters.get("session_id"))


@activities_router.message(Command("show_activity"))
async def show_activity_by_id(message: types.Message, command: CommandObject):
    admin_id = int(os.getenv("ADMIN_USER_ID"))
    if message.from_user.id != admin_id:
        await message.answer("⛔ Эта команда только для разработчика.")
        return

    activity_id_str = command.args
    if not activity_id_str or not activity_id_str.isdigit():
        await message.answer("⚠️ Укажи ID активности: /show_activity 87")
        return

    activity_id = int(activity_id_str)

    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if not response.data:
        await message.answer("😔 Не удалось найти активность.")
        return

    activity = response.data[0]

    summary = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])
    caption = f"🎲 Идея для родителя: *{activity['title']}*"
    full_text = (
        f"⏱️ {activity.get('time_required', 'не указано')} • "
        f"⚡️ {activity.get('energy', 'не указана')} • "
        f"📍 {activity.get('location', 'не указано')}\n\n"
        f"📦 Материалы: {activity.get('materials') or 'Не требуются'}\n\n"
        f"{activity.get('full_description', '')}\n\n"
        f"{summary}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Добавить в любимые ❤️",
                                 callback_data=f"favorite_add:{activity_id}"),
            InlineKeyboardButton(text="Показать ещё",
                                 callback_data="activity_next")
        ],
        [
            InlineKeyboardButton(
                text="Поделиться 💌",
                callback_data=f"share_activity:{activity_id}"),
            InlineKeyboardButton(text="Другие фильтры",
                                 callback_data="update_filters")
        ]
    ])

    try:
        await message.answer_photo(photo=activity["image_url"],
                                   caption=caption[:1024],
                                   parse_mode="Markdown")
        await message.answer(full_text,
                             parse_mode="Markdown",
                             reply_markup=keyboard)
    except Exception as e:
        await message.answer("⚠️ Ошибка при отправке активности.")
        print("Ошибка в show_activity_by_id:", e)

    try:
        log_event(user_id=message.from_user.id,
                  event_name="show_activity_by_id",
                  event_properties={
                      "activity_id": activity_id,
                      "age": activity.get("age_min"),
                      "time": activity.get("time_required"),
                      "energy": activity.get("energy"),
                      "location": activity.get("location")
                  },
                  session_id=user_data.get(message.from_user.id,
                                           {}).get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log show_activity_by_id: {e}")
