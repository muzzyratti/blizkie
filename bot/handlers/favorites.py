from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo, InputMediaPhoto

from db.supabase_client import add_favorite, get_favorites
from db.supabase_client import supabase

from utils.amplitude_logger import log_event
from .user_state import user_data

favorites_router = Router()

# Константа для подписи (экранированная)
VIRAL_SIGNATURE = "\n\n🏡 Найдено в @blizkie\_igry\_bot"

@favorites_router.callback_query(F.data.startswith("favorite_add:"))
async def favorite_add(callback: types.CallbackQuery):
    """
    Добавление активности в избранное.
    """
    activity_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # 1. Пишем в базу
    add_favorite(user_id=user_id, activity_id=activity_id)

    # 2. Логируем
    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    activity = response.data[0] if response.data else None

    try:
        log_event(
            user_id=user_id,
            event_name="favourites_add",
            event_properties={
                "activity_id": activity_id,
                "age": activity.get("age_min") if activity else None,
            },
            session_id=user_data.get(user_id, {}).get("session_id"),
        )
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_add: {e}")

    # 3. Обновляем клавиатуру
    new_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Убрать из любимых ✖️", callback_data=f"remove_fav:{activity_id}")],
            [InlineKeyboardButton(text="Следующую ⏩️", callback_data="activity_next")],
            [InlineKeyboardButton(text="Поменять фильтры 🎛️", callback_data="update_filters")],
            [InlineKeyboardButton(text="Поделитесь этой идеей ↩️", callback_data=f"share_activity:{activity_id}")],
            [InlineKeyboardButton(text="💬 Оставить отзыв", callback_data=f"feedback_button:{activity_id}")]
        ]
    )

    # 4. Восстанавливаем текст
    state = user_data.get(user_id, {})
    orig = state.get("current_activity_text") or {}
    orig_caption = orig.get("caption")
    orig_text = orig.get("text")
    msg = callback.message

    try:
        if orig_caption or orig_text:
            caption = orig_caption or ""
            text = orig_text or ""
            full_text = f"{caption}\n\n{text}".strip()

            if msg.photo or msg.video:
                if len(full_text) <= 1024:
                    await msg.edit_caption(caption=full_text, reply_markup=new_keyboard, parse_mode="Markdown")
                else:
                    await msg.edit_caption(caption=msg.caption, reply_markup=new_keyboard, parse_mode="Markdown")
            else:
                await msg.edit_text(text=full_text, reply_markup=new_keyboard, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            # Фоллбек
            if msg.photo or msg.video:
                await msg.edit_caption(caption=msg.caption, reply_markup=new_keyboard, parse_mode="Markdown")
            else:
                await msg.edit_text(text=msg.text, reply_markup=new_keyboard, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        print(f"[favorites] edit keyboard on favorite_add failed: {e}")

    await callback.answer("Добавлено в любимые ❤️")


async def list_favorites(message_or_callback: types.Message | types.CallbackQuery):
    """
    Вывод списка любимых активностей.
    """
    user_id = message_or_callback.from_user.id

    async def _send(mc, text, **kwargs):
        if isinstance(mc, types.CallbackQuery):
            return await mc.message.answer(text, **kwargs)
        else:
            return await mc.answer(text, **kwargs)

    async def _edit_or_send(mc, text):
        if isinstance(mc, types.CallbackQuery):
            try:
                await mc.message.edit_text(text)
            except Exception:
                await mc.message.answer(text)
            await mc.answer()
        else:
            await mc.answer(text)

    try:
        log_event(
            user_id=user_id,
            event_name="favourites_list",
            session_id=user_data.get(user_id, {}).get("session_id"),
        )
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_list: {e}")

    # Загружаем favorites
    favorites_response = (
        supabase.table("favorites")
        .select("activity_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    if not favorites_response.data:
        return await _edit_or_send(message_or_callback, "У вас пока нет любимых активностей 🌱")

    activity_ids = [fav["activity_id"] for fav in favorites_response.data]

    # Загружаем сами активности
    activities_response = (
        supabase.table("activities")
        .select("*")
        .in_("id", activity_ids)
        .execute()
    )

    if not activities_response.data:
        return await _send(message_or_callback, "Не удалось загрузить активности 😔")

    id_to_activity = {a["id"]: a for a in activities_response.data}
    sorted_activities = [id_to_activity[aid] for aid in activity_ids if aid in id_to_activity]

    await _edit_or_send(message_or_callback, "Ваши любимые активности:")

    for activity in sorted_activities:
        title = activity["title"]
        age = f"{activity.get('age_min', '?')}–{activity.get('age_max', '?')} лет"
        time_required = activity.get("time_required") or "-"
        energy = activity.get("energy") or "-"
        location = activity.get("location") or "-"

        text = (
            f"🎮 *{title}*\n"
            f"{age} • {time_required} • {energy} • {location}"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👉 Показать идею",
                        callback_data=f"fav_details:{activity['id']}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Убрать из любимых",
                        callback_data=f"remove_fav:{activity['id']}",
                    )
                ],
            ]
        )

        await _send(
            message_or_callback,
            text,
            parse_mode="Markdown",
            reply_markup=keyboard,
        )


@favorites_router.message(Command("favorites"))
async def show_favorites_command(message: types.Message):
    await list_favorites(message)


# --- НОВЫЙ ХЕНДЛЕР: Открывает L1 НОВЫМ сообщением (Full UI) ---
@favorites_router.callback_query(F.data.startswith("fav_details:"))
async def show_favorite_details(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    if not response.data:
        await callback.answer("Активность не найдена")
        return

    activity = response.data[0]

    # 1. Формируем полный текст (как в activities.py)
    summary = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])
    caption_title = f"🎲 *{activity['title']}*"

    author = activity.get("author")
    author_url = activity.get("source_url")
    author_block = ""
    if author and author_url:
        author_block = f"\n\n👤 Автор: [{author}]({author_url})"

    ugc_block = "\n\n💡 Есть идея игры? 👉 /suggest"

    full_text = (
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}"
        f"{author_block}"
        f"{VIRAL_SIGNATURE}"
        f"{ugc_block}"
    )

    # 2. Сохраняем состояние текста! 
    # (Чтобы если юзер нажмет "Убрать из любимых", сообщение не сломалось)
    user_state = user_data.setdefault(user_id, {})
    user_state["current_activity_text"] = {"caption": caption_title, "text": full_text}

    # 3. Полная клавиатура L1 (как ты просил)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Убрать из любимых ✖️", callback_data=f"remove_fav:{activity_id}")],
        [InlineKeyboardButton(text="Следующую ⏩️", callback_data="activity_next")],
        [InlineKeyboardButton(text="Поменять фильтры 🎛️", callback_data="update_filters")],
        [InlineKeyboardButton(text="Поделиться ↩️", callback_data=f"share_activity:{activity_id}")],
        [InlineKeyboardButton(text="💬 Оставить отзыв", callback_data=f"feedback_button:{activity_id}")]
    ])

    video_file_id = activity.get("video_file_id")
    image_url = activity.get("image_url")
    final_caption = f"{caption_title}\n\n{full_text}"

    # 4. Отправляем НОВЫМ сообщением (answer)
    try:
        if video_file_id and video_file_id.strip():
            if len(final_caption) <= 1024:
                await callback.message.answer_video(video=video_file_id, caption=final_caption, parse_mode="Markdown", reply_markup=keyboard)
            else:
                # Видео + Текст отдельно
                await callback.message.answer_video(video=video_file_id, caption=f"{caption_title}\n{VIRAL_SIGNATURE}", parse_mode="Markdown")
                chunk_size = 3500
                chunks = [full_text[i:i + chunk_size] for i in range(0, len(full_text), chunk_size)]
                for i, chunk in enumerate(chunks):
                    mk = keyboard if i == len(chunks) - 1 else None
                    await callback.message.answer(chunk, parse_mode="Markdown", reply_markup=mk, disable_web_page_preview=True)

        elif image_url and image_url.strip():
             if len(final_caption) <= 1024:
                await callback.message.answer_photo(photo=image_url, caption=final_caption, parse_mode="Markdown", reply_markup=keyboard)
             else:
                await callback.message.answer_photo(photo=image_url, caption=caption_title, parse_mode="Markdown")
                await callback.message.answer(full_text, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)
        else:
            await callback.message.answer(final_caption, parse_mode="Markdown", reply_markup=keyboard, disable_web_page_preview=True)

    except Exception as e:
        await callback.message.answer("Ошибка отображения")
        print(f"Fav details error: {e}")

    await callback.answer()


@favorites_router.callback_query(F.data.startswith("remove_fav:"))
async def remove_favorite(callback: types.CallbackQuery):
    """
    Удаление из избранного.
    """
    user_id = callback.from_user.id
    activity_id = int(callback.data.split(":")[1])

    # 1. Удаляем из БД
    supabase.table("favorites").delete().eq("user_id", user_id).eq("activity_id", activity_id).execute()

    try:
        log_event(
            user_id=user_id,
            event_name="favourites_remove",
            event_properties={"activity_id": activity_id},
            session_id=user_data.get(user_id, {}).get("session_id"),
        )
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_remove: {e}")

    msg = callback.message

    # 2. Определяем контекст (Список или Карточка?)
    is_list_view = False
    if msg.reply_markup and msg.reply_markup.inline_keyboard:
        # Если есть кнопка "Показать идею" (fav_details), значит это элемент списка
        if any("fav_details" in btn.callback_data for row in msg.reply_markup.inline_keyboard for btn in row):
            is_list_view = True

    if is_list_view:
        # Сценарий СПИСКА: Удаляем сообщение с этой карточкой
        try:
            await msg.delete()
        except:
            pass

        # Проверяем, остались ли любимые
        check = supabase.table("favorites").select("id").eq("user_id", user_id).execute()
        if not check.data:
            await callback.message.answer("У вас пока нет любимых активностей 🌱")

        await callback.answer("Удалено")
        return

    # Сценарий КАРТОЧКИ (L1): Меняем кнопку на "Добавить" и сохраняем текст
    new_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Добавить в любимые ❤️", callback_data=f"favorite_add:{activity_id}")],
            [InlineKeyboardButton(text="Следующую ⏩️", callback_data="activity_next")],
            [InlineKeyboardButton(text="Поменять фильтры 🎛️", callback_data="update_filters")],
            [InlineKeyboardButton(text="Поделитесь этой идеей ↩️", callback_data=f"share_activity:{activity_id}")],
            [InlineKeyboardButton(text="💬 Оставить отзыв", callback_data=f"feedback_button:{activity_id}")]
        ]
    )

    # Восстанавливаем текст (БЕЗОПАСНАЯ ЛОГИКА)
    state = user_data.get(user_id, {})
    orig = state.get("current_activity_text") or {}
    orig_caption = orig.get("caption")
    orig_text = orig.get("text")

    try:
        if orig_caption or orig_text:
            caption = orig_caption or ""
            text = orig_text or ""
            full_text = f"{caption}\n\n{text}".strip()

            if msg.photo or msg.video:
                if len(full_text) <= 1024:
                     await msg.edit_caption(caption=full_text, reply_markup=new_keyboard, parse_mode="Markdown")
                else:
                     await msg.edit_caption(caption=msg.caption, reply_markup=new_keyboard, parse_mode="Markdown")
            else:
                await msg.edit_text(text=full_text, reply_markup=new_keyboard, parse_mode="Markdown", disable_web_page_preview=True)
        else:
            # Фоллбек
            if msg.photo or msg.video:
                await msg.edit_caption(caption=msg.caption, reply_markup=new_keyboard, parse_mode="Markdown")
            else:
                await msg.edit_reply_markup(reply_markup=new_keyboard)

    except Exception as e:
        print(f"[favorites] edit keyboard on remove_fav failed: {e}")

    await callback.answer("Убрано из любимых")