from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaVideo, InputMediaPhoto
from aiogram.filters import Command, CommandObject
from aiogram.exceptions import TelegramBadRequest
from db.supabase_client import supabase
from utils.amplitude_logger import log_event as amplitude_log_event
from utils.session import ensure_filters
from .user_state import user_data
from db.seen import get_next_activity_with_filters
from datetime import datetime
from utils.paywall_guard import should_block_l1, should_block_l0
from handlers.paywall import send_universal_paywall
from utils.session_tracker import get_current_session_id
from config import ENV

activities_router = Router()

# === КОНСТАНТЫ ===
# Экранируем подчеркивания для Markdown
VIRAL_SIGNATURE = "\n\n🏡 Найдено в @blizkie\_igry\_bot"

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---


def get_activity_by_id(activity_id: int):
    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if response.data and len(response.data) > 0:
        return response.data[0]
    return None


def check_is_favorite(user_id: int, activity_id: int) -> bool:
    try:
        fav_response = supabase.table("favorites").select("id") \
            .eq("user_id", user_id).eq("activity_id", activity_id).execute()
        return len(fav_response.data) > 0
    except:
        return False


async def render_l0_card(message_or_callback,
                         activity,
                         user_id,
                         ctx,
                         is_edit=False):
    """
    Единая функция отрисовки L0 (Витрина).
    """
    is_favorite = check_is_favorite(user_id, activity["id"])
    fav_text = "В любимые ❤️" if not is_favorite else "Убрать из ❤️"
    fav_callback = f"favorite_add:{activity['id']}" if not is_favorite else f"remove_fav:{activity['id']}"

    # Текст L0 с виральной ссылкой
    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}"
            f"{VIRAL_SIGNATURE}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="Играем ▶️",
                callback_data=f"activity_details:{activity['id']}")
        ], [InlineKeyboardButton(text=fav_text, callback_data=fav_callback)],
        [
            InlineKeyboardButton(text="Следующую ⏩️",
                                 callback_data="activity_next")
        ],
        [
            InlineKeyboardButton(text="Поменять фильтры 🎛️",
                                 callback_data="update_filters")
        ]
    ])

    # === ЛОГИКА ВЫБОРА ВИДЕО ===
    video_file_id = None

    if ENV == "prod":
        # Если мы на проде: пытаемся взять prod-ID.
        # Если его нет (вдруг скрипт не доработал), берем старый как запасной вариант.
        video_file_id = activity.get("video_file_id_prod") or activity.get(
            "video_file_id")
    else:
        # Если мы на dev/local: берем ТОЛЬКО тестовый ID.
        # Prod-ID здесь не сработает, так как токен бота другой.
        video_file_id = activity.get("video_file_id")

    image_url = activity.get("image_url")

    # Получаем объект message, куда отвечать
    if isinstance(message_or_callback, types.CallbackQuery):
        message = message_or_callback.message
    else:
        message = message_or_callback

    # Логика отправки: Видео -> Фото -> Текст
    try:
        if video_file_id and video_file_id.strip():
            if is_edit and message.content_type == 'video':
                await message.edit_media(media=InputMediaVideo(
                    media=video_file_id, caption=text, parse_mode="Markdown"),
                                         reply_markup=keyboard)
            else:
                if is_edit: await message.delete()
                await message.answer_video(video=video_file_id,
                                           caption=text,
                                           parse_mode="Markdown",
                                           reply_markup=keyboard)

        elif image_url and image_url.strip():
            if is_edit and message.content_type == 'photo':
                await message.edit_media(media=InputMediaPhoto(
                    media=image_url, caption=text, parse_mode="Markdown"),
                                         reply_markup=keyboard)
            else:
                if is_edit: await message.delete()
                await message.answer_photo(photo=image_url,
                                           caption=text,
                                           parse_mode="Markdown",
                                           reply_markup=keyboard)

        else:
            if is_edit: await message.delete()
            await message.answer(text,
                                 parse_mode="Markdown",
                                 reply_markup=keyboard,
                                 disable_web_page_preview=True)

    except Exception as e:
        print(f"⚠️ L0 Render Error: {e}")
        await message.answer(text,
                             parse_mode="Markdown",
                             reply_markup=keyboard)


# --- ADMIN: /show_activity <ID>
@activities_router.message(Command("show_activity"))
async def show_activity_by_id_command(message: types.Message,
                                      command: CommandObject):
    if not command.args or not command.args.isdigit():
        await message.answer("⚠️ Используй формат: /show_activity <ID>")
        return

    activity_id = int(command.args)
    activity = get_activity_by_id(activity_id)
    if not activity:
        await message.answer(f"❌ Активность {activity_id} не найдена.")
        return

    await render_l0_card(message,
                         activity,
                         message.from_user.id,
                         ctx={},
                         is_edit=False)


# --- L0 Handler: START
@activities_router.callback_query(F.data == "activity_start")
async def send_activity(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)

    if should_block_l0(user_id):
        await send_universal_paywall(callback,
                                     reason="l0_limit",
                                     user_id=user_id,
                                     session_id=session_id)
        return

    activity_id, was_reset = get_next_activity_with_filters(
        user_id=user_id,
        age_min=int(ctx["age_min"]),
        age_max=int(ctx["age_max"]),
        time_required=ctx["time_required"],
        energy=ctx["energy"],
        location=ctx["location"])

    if not activity_id:
        await callback.message.answer(
            "😔 Нет идей для таких условий. Попробуйте изменить фильтры.",
            disable_web_page_preview=True)
        return

    activity = get_activity_by_id(activity_id)
    if not activity:
        await callback.message.answer("😔 Ошибка загрузки идеи.",
                                      disable_web_page_preview=True)
        return

    await render_l0_card(callback, activity, user_id, ctx, is_edit=True)

    supabase.table("seen_activities").upsert({
        "user_id":
        user_id,
        "activity_id":
        activity["id"],
        "age_min":
        ctx["age_min"],
        "age_max":
        ctx["age_max"],
        "time_required":
        ctx["time_required"],
        "energy":
        ctx["energy"],
        "location":
        ctx["location"],
        "level":
        "l0",
        "seen_at":
        datetime.now().isoformat()
    }).execute()

    amplitude_log_event(user_id=user_id,
                        event_name="show_activity_L0",
                        event_properties={"activity_id": activity["id"]},
                        session_id=session_id)
    await callback.answer()


# --- L0 Handler: NEXT
@activities_router.callback_query(F.data == "activity_next")
async def show_next_activity(callback: types.CallbackQuery):
    await send_activity(callback)


# --- /next команда
@activities_router.message(Command("next"))
async def next_command_handler(message: types.Message):
    user_id = message.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)

    if should_block_l0(user_id):
        await send_universal_paywall(message,
                                     reason="l0_limit",
                                     user_id=user_id,
                                     session_id=session_id)
        return

    activity_id, _ = get_next_activity_with_filters(
        user_id=user_id,
        age_min=int(ctx["age_min"]),
        age_max=int(ctx["age_max"]),
        time_required=ctx["time_required"],
        energy=ctx["energy"],
        location=ctx["location"])

    if not activity_id:
        await message.answer("😔 Нет идей для таких условий.",
                             disable_web_page_preview=True)
        return

    activity = get_activity_by_id(activity_id)
    if not activity: return

    await render_l0_card(message, activity, user_id, ctx, is_edit=False)

    amplitude_log_event(user_id=user_id,
                        event_name="show_activity_L0_next_command",
                        event_properties={
                            "activity_id": activity["id"],
                            "age_min": ctx["age_min"],
                            "age_max": ctx["age_max"],
                            "time_required": ctx["time_required"],
                            "energy": ctx["energy"],
                            "location": ctx["location"]
                        },
                        session_id=session_id)

    supabase.table("seen_activities").upsert({
        "user_id":
        user_id,
        "activity_id":
        activity["id"],
        "age_min":
        ctx["age_min"],
        "age_max":
        ctx["age_max"],
        "time_required":
        ctx["time_required"],
        "energy":
        ctx["energy"],
        "location":
        ctx["location"],
        "level":
        "l0",
        "seen_at":
        datetime.now().isoformat()
    }).execute()


# --- L1: ПРЕВРАЩЕНИЕ В ПОДРОБНУЮ (UPDATE IN PLACE)
@activities_router.callback_query(F.data.startswith("activity_details:"))
async def show_activity_details(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)
    activity_id = int(callback.data.split(":")[1])

    if should_block_l1(user_id):
        ctx = user_data.setdefault(user_id, {})
        ctx["last_paywall_reason"] = "l1_limit"
        await send_universal_paywall(callback,
                                     reason="l1_limit",
                                     user_id=user_id,
                                     session_id=session_id)
        return

    activity = get_activity_by_id(activity_id)
    if not activity:
        await callback.answer("Ошибка загрузки", show_alert=True)
        return

    is_favorite = check_is_favorite(user_id, activity_id)

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
        f"{ugc_block}")

    user_state = user_data.setdefault(user_id, {})
    user_state["current_activity_text"] = {
        "caption": caption_title,
        "text": full_text
    }

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="В любимые ❤️" if not is_favorite else "Убрать из ❤️",
                callback_data=
                f"{'favorite_add' if not is_favorite else 'remove_fav'}:{activity_id}"
            )
        ],
        [
            InlineKeyboardButton(text="Следующую ⏩️",
                                 callback_data="activity_next")
        ],
        [
            InlineKeyboardButton(text="Поменять фильтры 🎛️",
                                 callback_data="update_filters")
        ],
        [
            InlineKeyboardButton(text="Поделиться ↩️",
                                 callback_data=f"share_activity:{activity_id}")
        ],
        [
            InlineKeyboardButton(
                text="💬 Оставить отзыв",
                callback_data=f"feedback_button:{activity_id}")
        ]
    ])

    message = callback.message
    has_media = message.content_type in ['video', 'photo']
    final_caption = f"{caption_title}\n\n{full_text}"

    try:
        if has_media:
            if len(final_caption) <= 1024:
                await message.edit_caption(caption=final_caption,
                                           parse_mode="Markdown",
                                           reply_markup=keyboard)
            else:
                # Если текст длинный
                if message.content_type == 'video':
                    # Для видео убираем лишний текст "Инструкция ниже", оставляем только подпись
                    short_caption = f"{caption_title}{VIRAL_SIGNATURE}"

                await message.edit_caption(caption=short_caption,
                                           parse_mode="Markdown")

                chunk_size = 3500
                chunks = [
                    full_text[i:i + chunk_size]
                    for i in range(0, len(full_text), chunk_size)
                ]
                for i, chunk in enumerate(chunks):
                    markup = keyboard if i == len(chunks) - 1 else None
                    await message.answer(chunk,
                                         parse_mode="Markdown",
                                         reply_markup=markup,
                                         disable_web_page_preview=True)
        else:
            await message.edit_text(f"{caption_title}\n\n{full_text}",
                                    parse_mode="Markdown",
                                    reply_markup=keyboard,
                                    disable_web_page_preview=True)

    except TelegramBadRequest as e:
        print(f"Edit error (L1): {e}")
        await message.answer(final_caption[:3500],
                             parse_mode="Markdown",
                             reply_markup=keyboard)

    supabase.table("seen_activities").upsert({
        "user_id":
        user_id,
        "activity_id":
        activity_id,
        "age_min":
        activity.get("age_min"),
        "age_max":
        activity.get("age_max"),
        "time_required":
        activity.get("time_required"),
        "energy":
        activity.get("energy"),
        "location":
        activity.get("location"),
        "level":
        "l1",
        "seen_at":
        datetime.now().isoformat()
    }).execute()

    ctx["l1_counter"] = int(ctx.get("l1_counter", 0)) + 1
    from handlers.feedback_activity import maybe_prompt_auto_feedback
    await maybe_prompt_auto_feedback(user_id=user_id,
                                     activity_id=activity_id,
                                     ctx=ctx,
                                     bot=callback.bot)

    amplitude_log_event(user_id=user_id,
                        event_name="show_activity_L1",
                        event_properties={
                            "activity_id": activity_id,
                            "has_video": bool(activity.get("video_file_id")),
                            "age_min": activity.get("age_min"),
                            "age_max": activity.get("age_max")
                        },
                        session_id=session_id)

    try:
        await callback.answer()
    except:
        pass
