from aiogram import Router, types, F
from db.supabase_client import supabase
from utils.amplitude_logger import log_event
from .start import user_data

share_router = Router()


@share_router.callback_query(F.data.startswith("share_activity:"))
async def share_activity(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])

    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if not response.data:
        await callback.answer("Не удалось найти активность 😔")
        return

    activity = response.data[0]

    # базовые поля
    age_str = f"{activity['age_min']}-{activity['age_max']} лет" if activity.get(
        "age_min") and activity.get("age_max") else "не указан"
    time = activity.get("time_required", "не указано")
    energy = activity.get("energy", "не указана")
    location = activity.get("location", "не указано")
    materials = activity.get("materials", None)
    full_description = activity.get('full_description', '')
    summary_lines = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])

    # --- Автор и ссылка (Markdown-safe) ---
    def build_author_block_md(author, url):
        if not author:
            return ""
        if url:
            return f"[{author}]({url})"
        return author

    author_block = build_author_block_md(
        activity.get("author"),
        activity.get("source_url")
    )

    footer = "👉 Такие идеи даёт бот @blizkie\\_igry\\_bot — там быстро найдете что поделать с ребёнком прямо сейчас."

    materials_text = f"📦 Материалы: {materials}" if materials else ""

    # caption — только заголовок
    caption = f"🎲 Идея для родителя: *{activity['title']}*"

    # полный текст в нужном порядке
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

        # режем на chunk’и
        chunk_size = 3500
        chunks = [
            full_message[i:i + chunk_size]
            for i in range(0, len(full_message), chunk_size)
        ]

        if image_url and image_url.strip():
            # 1) капшен (до 1024 символов)
            first_chunk = chunks[0]
            await callback.message.answer_photo(
                photo=image_url,
                caption=first_chunk[:1024],
                parse_mode="Markdown"
            )

            # 2) остатки
            remaining_parts = []

            if len(first_chunk) > 1024:
                remaining_parts.append(first_chunk[1024:])

            if len(chunks) > 1:
                remaining_parts.extend(chunks[1:])

            # отправляем частями
            for part in remaining_parts:
                subchunks = [
                    part[i:i + chunk_size]
                    for i in range(0, len(part), chunk_size)
                ]
                for sc in subchunks:
                    await callback.message.answer(sc, parse_mode="Markdown")

        else:
            # без картинки
            for part in chunks:
                await callback.message.answer(part, parse_mode="Markdown")

    except Exception as e:
        await callback.message.answer("⚠️ Не удалось поделиться идеей.")
        print("Ошибка при отправке идеи:", e)

    # логирование
    try:
        log_event(
            user_id=callback.from_user.id,
            event_name="share_activity",
            event_properties={
                "activity_id": activity_id,
                "age": activity.get("age_min"),
                "time": activity.get("time_required"),
                "energy": activity.get("energy"),
                "location": activity.get("location")
            },
            session_id=user_data.get(callback.from_user.id, {}).get("session_id")
        )
    except Exception as e:
        print(f"[Amplitude] Failed to log share_activity: {e}")

    await callback.answer("Можно переслать идею 💌")
