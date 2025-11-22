from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from db.supabase_client import add_favorite, get_favorites  # get_favorites пока не используется, но не трогаю
from db.supabase_client import supabase

from utils.amplitude_logger import log_event
from .start import user_data

favorites_router = Router()


@favorites_router.callback_query(F.data.startswith("favorite_add:"))
async def favorite_add(callback: types.CallbackQuery):
    """
    Добавление активности в избранное.
    Для L1-карточки: меняем только клавиатуру, текст/форматирование не трогаем
    (берём оригинальный caption/text из user_data["current_activity_text"]).
    """
    activity_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    # Добавляем в избранное
    add_favorite(user_id=user_id, activity_id=activity_id)

    # Берём активность для логов, как и раньше
    response = (
        supabase.table("activities")
        .select("*")
        .eq("id", activity_id)
        .execute()
    )
    activity = response.data[0] if response.data else None

    try:
        log_event(
            user_id=user_id,
            event_name="favourites_add",
            event_properties={
                "activity_id": activity_id,
                "age": activity.get("age_min") if activity else None,
                "time": activity.get("time_required") if activity else None,
                "energy": activity.get("energy") if activity else None,
                "location": activity.get("location") if activity else None,
            },
            session_id=user_data.get(user_id, {}).get("session_id"),
        )
    except Exception as e:
        print(f"[Amplitude] Failed to log favourites_add: {e}")

    # Клавиатура как в show_activity_details, но уже is_favorite = True
    new_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Убрать из любимых ✖️",
                    callback_data=f"remove_fav:{activity_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Следующую ⏩️",
                    callback_data="activity_next",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Поменять фильтры 🎛️",
                    callback_data="update_filters",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Поделитесь этой идеей ↩️",
                    callback_data=f"share_activity:{activity_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Оставить отзыв",
                    callback_data=f"feedback_button:{activity_id}",
                )
            ],
        ]
    )

    # Пытаемся взять оригинальный caption/text, сохранённый в show_activity_details
    state = user_data.get(user_id, {})
    orig = state.get("current_activity_text") or {}
    orig_caption = orig.get("caption")
    orig_text = orig.get("text")

    try:
        msg = callback.message

        if orig_caption or orig_text:
            # У нас есть исходные тексты — собираем полный markdown-текст
            caption = orig_caption or ""
            text = orig_text or ""
            full_text = f"{caption}\n\n{text}".strip()

            if msg.photo:
                # Короткий случай: caption+text <= 1024 (как в show_activity_details)
                # Здесь можно безопасно класть всё в caption
                await msg.edit_caption(
                    caption=full_text,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                )
            else:
                # Последний текстовый блок (без фото) — восстанавливаем весь текст
                await msg.edit_text(
                    text=full_text,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
        else:
            # Фоллбек на случай, если почему-то нет current_activity_text
            if msg.photo:
                await msg.edit_caption(
                    caption=msg.caption,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                )
            else:
                await msg.edit_text(
                    text=msg.text,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
    except Exception as e:
        print(f"[favorites] edit keyboard on favorite_add failed: {e}")

    await callback.answer("Добавлено в любимые ❤️")


async def list_favorites(message_or_callback: types.Message | types.CallbackQuery):
    """
    Список любимых активностей.
    Показываем заголовок + по одной карточке на каждую активность.
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

    # Логирование
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
        return await _edit_or_send(
            message_or_callback, "У вас пока нет любимых активностей 🌱"
        )

    activity_ids = [fav["activity_id"] for fav in favorites_response.data]

    activities_response = (
        supabase.table("activities")
        .select("*")
        .in_("id", activity_ids)
        .execute()
    )

    if not activities_response.data:
        return await _send(
            message_or_callback, "Не удалось загрузить активности 😔"
        )

    id_to_activity = {a["id"]: a for a in activities_response.data}
    sorted_activities = [
        id_to_activity[aid] for aid in activity_ids if aid in id_to_activity
    ]

    # Заголовок
    await _edit_or_send(message_or_callback, "Ваши любимые активности:")

    # Отправляем каждую карточку
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
                        callback_data=f"activity_details:{activity['id']}",
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


@favorites_router.callback_query(F.data.startswith("remove_fav:"))
async def remove_favorite(callback: types.CallbackQuery):
    """
    Удаление из избранного:
    - если это карточка из списка "Мои любимые" — удаляем сообщение;
      при пустом списке показываем "нет любимых".
    - если это L1-карточка — меняем только клавиатуру
      (кнопка → "Добавить в любимые ❤️"), текст/форматирование восстанавливаем
      из user_data["current_activity_text"].
    """
    user_id = callback.from_user.id
    activity_id = int(callback.data.split(":")[1])

    # Удаляем из favorites в любом случае
    supabase.table("favorites") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("activity_id", activity_id) \
        .execute()

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
    kb = msg.reply_markup

    # Определяем, это карточка из списка "Мои любимые" или L1-карточка
    is_favorites_list_card = False
    try:
        if kb and kb.inline_keyboard:
            rows = kb.inline_keyboard
            # В списке "Мои любимые" у нас 2 строки:
            # [ "👉 Показать идею" ], [ "❌ Убрать из любимых" ]
            if (
                len(rows) == 2
                and len(rows[0]) == 1
                and len(rows[1]) == 1
                and (rows[0][0].callback_data or "").startswith("activity_details:")
                and (rows[1][0].callback_data or "").startswith("remove_fav:")
            ):
                is_favorites_list_card = True
    except Exception:
        is_favorites_list_card = False

    if is_favorites_list_card:
        # 🔹 ВАРИАНТ 1: карточка из списка "Мои любимые"
        # Просто удаляем её и, если список опустел, показываем сообщение
        try:
            await msg.delete()
        except Exception:
            pass

        favorites_response = (
            supabase.table("favorites")
            .select("activity_id")
            .eq("user_id", user_id)
            .execute()
        )

        if not favorites_response.data:
            await callback.message.answer(
                "У вас пока нет любимых активностей 🌱"
            )

        await callback.answer()
        return

    # 🔹 ВАРИАНТ 2: L1-карточка (подробная идея)
    # Меняем только клавиатуру: первая кнопка → "Добавить в любимые ❤️"
    new_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Добавить в любимые ❤️",
                    callback_data=f"favorite_add:{activity_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Следующую ⏩️",
                    callback_data="activity_next",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Поменять фильтры 🎛️",
                    callback_data="update_filters",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Поделитесь этой идеей ↩️",
                    callback_data=f"share_activity:{activity_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Оставить отзыв",
                    callback_data=f"feedback_button:{activity_id}",
                )
            ],
        ]
    )

    # Пытаемся взять оригинальный caption/text
    state = user_data.get(user_id, {})
    orig = state.get("current_activity_text") or {}
    orig_caption = orig.get("caption")
    orig_text = orig.get("text")

    try:
        if orig_caption or orig_text:
            caption = orig_caption or ""
            text = orig_text or ""
            full_text = f"{caption}\n\n{text}".strip()

            if msg.photo:
                await msg.edit_caption(
                    caption=full_text,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                )
            else:
                await msg.edit_text(
                    text=full_text,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
        else:
            # Фоллбек, если по какой-то причине нет current_activity_text
            if msg.photo:
                await msg.edit_caption(
                    caption=msg.caption,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                )
            else:
                await msg.edit_text(
                    text=msg.text,
                    reply_markup=new_keyboard,
                    parse_mode="Markdown",
                    disable_web_page_preview=True,
                )
    except Exception as e:
        print(f"[favorites] edit keyboard on remove_fav failed: {e}")

    await callback.answer("Убрано из любимых")
