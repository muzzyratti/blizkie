
from aiogram import Router, types, F
from db.supabase_client import supabase
from utils.amplitude_logger import log_event
from .start import user_data 

share_router = Router()

@share_router.callback_query(F.data.startswith("share_activity:"))
async def share_activity(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])

    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    if not response.data:
        await callback.answer("Не удалось найти активность 😔")
        return

    activity = response.data[0]

    age_str = f"{activity['age_min']}-{activity['age_max']} лет" if activity.get("age_min") and activity.get("age_max") else "не указан"
    time = activity.get("time_required", "не указано")
    energy = activity.get("energy", "не указана")
    location = activity.get("location", "не указано")
    materials = activity.get("materials", None)
    short_description = activity.get('short_description', '')
    full_description = activity.get('full_description', '')
    summary_lines = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])
    footer = "👉 Такие идеи даёт бот @blizkie\\_igry\\_bot — посмотрите, вдруг откликнется"

    materials_text = f"📦 Материалы: {materials}\n\n" if materials else ""

    # caption — только заголовок
    caption = f"🎲 Идея для родителя: *{activity['title']}*"

    # полный текст в нужном порядке
    text = (
        f"🧒 {age_str}\n"
        f"⏳ {time}\n"
        f"⚡️ {energy}\n"
        f"📍 {location}\n\n"
        f"{materials_text}"
        f"{full_description}\n\n"
        f"{summary_lines}\n\n"
        f"{footer}"
    )

    try:
        if len(caption) + len(text) <= 1024:
            await callback.message.answer_photo(
                photo=activity["image_url"],
                caption=f"{caption}\n\n{text}",
                parse_mode="Markdown"
            )
        else:
            await callback.message.answer_photo(
                photo=activity["image_url"],
                caption=caption[:1024],
                parse_mode="Markdown"
            )
            await callback.message.answer(text, parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer("⚠️ Не удалось поделиться идеей.")
        print("Ошибка при отправке идеи:", e)

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
                  session_id=user_data.get(callback.from_user.id, {}).get("session_id"))
    except Exception as e:
        print(f"[Amplitude] Failed to log share_activity: {e}")

    await callback.answer("Можно переслать идею 💌")
