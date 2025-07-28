from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db.supabase_client import add_favorite, get_favorites
from db.supabase_client import supabase

from utils.amplitude_logger import log_event
from .start import user_data

favorites_router = Router()


@favorites_router.callback_query(F.data.startswith("favorite_add:"))
async def favorite_add(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    add_favorite(user_id=user_id, activity_id=activity_id)

    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if not response.data:
        await callback.message.answer("😔 Не удалось найти активность.")
        await callback.answer()
        return

    activity = response.data[0]

    try:
        log_event(user_id=user_id,
                  event_name="favourites_add",
                  event_properties={
                      "activity_id": activity_id,
                      "age": activity.get("age_min"),
                      "time": activity.get("time_required"),
                      "energy": activity.get("energy"),
                      "location": activity.get("location")
                  },
                  session_id=user_data.get(user_id, {}).get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_add: {e}")

    summary = "\n".join([f"💡 {s}" for s in (activity['summary'] or [])])
    text = (
        f"🎲 *{activity['title']}*\n\n"
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}")

    row1 = [
        InlineKeyboardButton(text="Убрать из любимых ✖️",
                             callback_data=f"remove_fav:{activity_id}"),
        InlineKeyboardButton(text="Покажи еще идею",
                             callback_data="activity_next")
    ]
    row2 = [
        InlineKeyboardButton(text="Хочу другие советы",
                             callback_data="update_filters"),
        InlineKeyboardButton(text="Поделиться идеей 💌",
                             callback_data=f"share_activity:{activity_id}")
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[row1, row2])

    try:
        await callback.message.edit_caption(caption=text,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)
    except Exception:
        await callback.message.answer_photo(photo=activity["image_url"],
                                            caption=text,
                                            parse_mode="Markdown",
                                            reply_markup=keyboard)

    await callback.answer("Добавлено в любимые ❤️")


async def list_favorites(message_or_callback: types.Message
                         | types.CallbackQuery):
    user_id = message_or_callback.from_user.id

    try:
        log_event(user_id=user_id,
                  event_name="favourites_list",
                  session_id=user_data.get(user_id, {}).get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_list: {e}")

    favorites_response = supabase.table("favorites") \
        .select("activity_id") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    if not favorites_response.data:
        text = "У вас пока нет любимых активностей 🌱"
        if isinstance(message_or_callback, types.CallbackQuery):
            try:
                await message_or_callback.message.edit_text(text)
            except Exception:
                await message_or_callback.message.answer(text)
            await message_or_callback.answer()
        else:
            await message_or_callback.answer(text)
        return

    activity_ids = [fav["activity_id"] for fav in favorites_response.data]

    activities_response = supabase.table("activities") \
        .select("*") \
        .in_("id", activity_ids) \
        .execute()

    if not activities_response.data:
        await message_or_callback.answer("Не удалось загрузить активности 😔")
        return

    id_to_activity = {a["id"]: a for a in activities_response.data}
    sorted_activities = [
        id_to_activity[aid] for aid in activity_ids if aid in id_to_activity
    ]

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=activity["title"],
            callback_data=f"activity_details:{activity['id']}"),
        InlineKeyboardButton(text="✖️",
                             callback_data=f"remove_fav:{activity['id']}")
    ] for activity in sorted_activities])

    if isinstance(message_or_callback, types.CallbackQuery):
        try:
            await message_or_callback.message.edit_text(
                "Ваши любимые активности:", reply_markup=keyboard)
        except Exception:
            await message_or_callback.message.answer(
                "Ваши любимые активности:", reply_markup=keyboard)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer("Ваши любимые активности:",
                                         reply_markup=keyboard)


@favorites_router.message(Command("favorites"))
async def show_favorites_command(message: types.Message):
    await list_favorites(message)


@favorites_router.callback_query(F.data.startswith("remove_fav:"))
async def remove_favorite(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    activity_id = int(callback.data.split(":")[1])

    supabase.table("favorites") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("activity_id", activity_id) \
        .execute()

    try:
        log_event(user_id=user_id,
                  event_name="favourites_remove",
                  event_properties={"activity_id": activity_id},
                  session_id=user_data.get(user_id, {}).get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_remove: {e}")

    await list_favorites(callback)


@favorites_router.callback_query(F.data.startswith("share_activity:"))
async def share_activity(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])

    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if not response.data:
        await callback.answer("Не удалось найти активность 😔")
        return

    activity = response.data[0]

    age_str = f"{activity['age_min']}-{activity['age_max']} лет" if activity.get(
        "age_min") and activity.get("age_max") else "не указан"
    time = activity.get("time_required", "не указано")
    energy = activity.get("energy", "не указана")
    location = activity.get("location", "не указано")
    materials = activity.get("materials", None)

    summary_lines = "\n".join(
        [f"💡 {s}" for s in (activity.get("summary") or [])])
    materials_text = f"📦 Материалы: {materials}\n\n" if materials else ""

    text = (
        f"🎲 *{activity['title']}*\n\n"
        f"🧒 Возраст: {age_str}\n"
        f"⏳ Время: {time}\n"
        f"⚡️ Энергия: {energy}\n"
        f"📍 Место: {location}\n\n"
        f"{materials_text}"
        f"{activity.get('short_description', '')}\n\n"
        f"{activity.get('full_description', '')}\n\n"
        f"{summary_lines}\n\n"
        f"👉 Такие идеи даёт бот [@blizkie_igry_bot](https://t.me/blizkie_igry_bot) — посмотрите, вдруг откликнется"
    )

    try:
        await callback.message.answer_photo(photo=activity["image_url"],
                                            caption=text,
                                            parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer("⚠️ Не удалось поделиться идеей.")
        print("Ошибка при отправке идеи:", e)

    # ✅ Логирование события
    try:
        log_event(user_id=callback.from_user.id,
                  event_name="share_activity",
                  event_properties={
                      "activity_id": activity_id,
                      "age": activity.get("age_min"),
                      "time": activity.get("time_required"),
                      "energy": activity.get("energy"),
                      "location": activity.get("location")
                  },
                  session_id=user_data.get(callback.from_user.id,
                                           {}).get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log share_activity: {e}")

    await callback.answer("Можно переслать идею 💌")
