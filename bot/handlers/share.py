from aiogram import Router, types, F
from db.supabase_client import supabase
from utils.amplitude_logger import log_event
from .start import user_data

share_router = Router()

# Подпись
VIRAL_SIGNATURE = "🏡 Найдено в @blizkie\_igry\_bot"

@share_router.callback_query(F.data.startswith("share_activity:"))
async def share_activity(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])

    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    if not response.data:
        await callback.answer("Не удалось найти активность 😔")
        return

    activity = response.data[0]

    age_str = f"{activity['age_min']}-{activity['age_max']} лет" if activity.get("age_min") else "не указан"
    time = activity.get("time_required", "не указано")
    energy = activity.get("energy", "не указана")
    location = activity.get("location", "не указано")
    materials = activity.get("materials", None)
    full_description = activity.get('full_description', '')
    summary_lines = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])

    def build_author_block_md(author, url):
        if not author: return ""
        if url: return f"[{author}]({url})"
        return author

    author_block = build_author_block_md(activity.get("author"), activity.get("source_url"))

    # Текст с подписью
    footer = f"{VIRAL_SIGNATURE}"

    materials_text = f"📦 Материалы: {materials}" if materials else ""
    caption = f"🎲 Идея для родителя: *{activity['title']}*"

    text_parts = [
        f"🧒 {age_str}",
        f"⏳ {time}",
        f"⚡️ {energy}",
        f"📍 {location}",
        "",
        materials_text,
        "",
        full_description,
        "",
        summary_lines,
        "",
    ]

    if author_block:
        text_parts.append(author_block)
        text_parts.append("")

    text_parts.append(footer)
    text = "\n".join(text_parts)

    try:
        image_url = activity.get("image_url")
        full_message = f"{caption}\n\n{text}"

        chunk_size = 3500
        chunks = [full_message[i:i + chunk_size] for i in range(0, len(full_message), chunk_size)]

        if image_url and image_url.strip():
            first_chunk = chunks[0]
            await callback.message.answer_photo(
                photo=image_url,
                caption=first_chunk[:1024],
                parse_mode="Markdown"
            )

            remaining_text = full_message[1024:] if len(first_chunk) > 1024 else ""
            if len(chunks) > 1:
                remaining_text += "".join(chunks[1:])

            if remaining_text:
                # Шлем остатки
                subchunks = [remaining_text[i:i + chunk_size] for i in range(0, len(remaining_text), chunk_size)]
                for sc in subchunks:
                    await callback.message.answer(sc, parse_mode="Markdown")
        else:
            for part in chunks:
                await callback.message.answer(part, parse_mode="Markdown")

    except Exception as e:
        await callback.message.answer("⚠️ Не удалось поделиться идеей.")
        print("Ошибка при отправке идеи:", e)

    # Logging
    try:
        log_event(
            user_id=callback.from_user.id,
            event_name="share_activity",
            event_properties={"activity_id": activity_id},
            session_id=user_data.get(callback.from_user.id, {}).get("session_id")
        )
    except:
        pass

    await callback.answer("Можно переслать идею 💌")