from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from db.supabase_client import get_activity, supabase, TIME_MAP, ENERGY_MAP, location_MAP
from utils.amplitude_logger import log_event as amplitude_log_event
from utils.session import ensure_filters
from .user_state import user_data
from db.seen import get_next_activity_with_filters
from datetime import datetime
from utils.paywall_guard import should_block_l1, should_block_l0
from handlers.paywall import send_universal_paywall
from utils.session_tracker import get_current_session_id

activities_router = Router()


def get_activity_by_id(activity_id: int):
    response = supabase.table("activities").select("*").eq("id", activity_id).single().execute()
    return response.data


# --- L0 карточка (короткая)
@activities_router.callback_query(F.data == "activity_start")
async def send_activity(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)

    # PAYWALL: если превышен лимит L0 (15)
    if should_block_l0(user_id):
        await send_universal_paywall(callback, reason="l0_limit", user_id=user_id, session_id=session_id)
        return

    activity_id, was_reset = get_next_activity_with_filters(
        user_id=user_id,
        age_min=int(ctx["age_min"]),
        age_max=int(ctx["age_max"]),
        time_required=ctx["time_required"],
        energy=ctx["energy"],
        location=ctx["location"]
    )

    if activity_id is None:
        await callback.message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.",
                                      disable_web_page_preview=True)
        return

    activity = get_activity_by_id(activity_id)
    if not activity:
        await callback.message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.",
                                      disable_web_page_preview=True)
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Расскажи как играть", callback_data=f"activity_details:{activity['id']}")],
        [InlineKeyboardButton(text="Покажи еще идею", callback_data="activity_next")],
        [InlineKeyboardButton(text="Хочу другие фильтры", callback_data="update_filters")]
    ])

    amplitude_log_event(
        user_id=user_id,
        event_name="show_activity_L0",
        event_properties={
            "activity_id": activity["id"],
            "age_min": ctx["age_min"],
            "age_max": ctx["age_max"],
            "time_required": ctx["time_required"],
            "energy": ctx["energy"],
            "location": ctx["location"]
        },
        session_id=session_id
    )

    image_url = activity.get("image_url")
    if image_url and image_url.strip():
        await callback.message.answer_photo(photo=image_url, caption=text, parse_mode="Markdown",
                                            reply_markup=keyboard, disable_web_page_preview=True)
    else:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard,
                                      disable_web_page_preview=True)

    supabase.table("seen_activities").upsert({
        "user_id": user_id,
        "activity_id": activity["id"],
        "age_min": ctx["age_min"],
        "age_max": ctx["age_max"],
        "time_required": ctx["time_required"],
        "energy": ctx["energy"],
        "location": ctx["location"],
        "level": "l0",
        "seen_at": datetime.now().isoformat()
    }).execute()


# --- L1 карточка (подробная)
@activities_router.callback_query(F.data.startswith("activity_details:"))
async def show_activity_details(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)
    activity_id = int(callback.data.split(":")[1])

    # PAYWALL: если превышен лимит L1 (5)
    if should_block_l1(user_id):
        ctx = user_data.setdefault(user_id, {})
        ctx["last_paywall_reason"] = "l1_limit"
        await send_universal_paywall(callback, reason="l1_limit", user_id=user_id, session_id=session_id)
        return

    response = supabase.table("activities").select("*").eq("id", activity_id).execute()
    if not response.data:
        await callback.message.answer("😔 Не удалось найти подробности активности.",
                                      disable_web_page_preview=True)
        await callback.answer()
        return

    activity = response.data[0]
    fav_response = supabase.table("favorites").select("id") \
        .eq("user_id", user_id).eq("activity_id", activity_id).execute()
    is_favorite = len(fav_response.data) > 0

    summary = "\n".join([f"💡 {s}" for s in (activity.get("summary") or [])])
    caption = f"🎲 *{activity['title']}*"
    text = (
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}"
    )

    # Сохраняем оригинальные тексты для корректного изменения клавиатуры
    user_state = user_data.setdefault(user_id, {})
    user_state["current_activity_text"] = {
        "caption": caption,
        "text": text
    }

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Добавить в любимые ❤️" if not is_favorite else "Убрать из любимых ✖️",
            callback_data=f"{'favorite_add' if not is_favorite else 'remove_fav'}:{activity_id}")],
        [InlineKeyboardButton(text="Покажи еще идею", callback_data="activity_next")],
        [InlineKeyboardButton(text="Хочу другие фильтры", callback_data="update_filters")],
        [InlineKeyboardButton(text="Поделиться идеей 💌", callback_data=f"share_activity:{activity_id}")],
        [InlineKeyboardButton(text="💬 Оставить отзыв", callback_data=f"feedback_button:{activity_id}")]
    ])

    try:
        image_url = activity.get("image_url")
        if image_url and image_url.strip():
            if len(caption) + len(text) <= 1024:
                await callback.message.answer_photo(photo=image_url, caption=f"{caption}\n\n{text}",
                                                    parse_mode="Markdown", reply_markup=keyboard,
                                                    disable_web_page_preview=True)
            else:
                await callback.message.answer_photo(photo=image_url, caption=caption[:1024],
                                                    parse_mode="Markdown", disable_web_page_preview=True)
                chunk_size = 3500
                chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
                for i, chunk in enumerate(chunks):
                    if i < len(chunks) - 1:
                        await callback.message.answer(chunk, parse_mode="Markdown",
                                                      disable_web_page_preview=True)
                    else:
                        await callback.message.answer(chunk, parse_mode="Markdown",
                                                      reply_markup=keyboard,
                                                      disable_web_page_preview=True)
        else:
            long_text = f"{caption}\n\n{text}"
            chunk_size = 3500
            chunks = [long_text[i:i + chunk_size] for i in range(0, len(long_text), chunk_size)]
            for i, chunk in enumerate(chunks):
                if i < len(chunks) - 1:
                    await callback.message.answer(chunk, parse_mode="Markdown",
                                                  disable_web_page_preview=True)
                else:
                    await callback.message.answer(chunk, parse_mode="Markdown",
                                                  reply_markup=keyboard,
                                                  disable_web_page_preview=True)
    except Exception as e:
        await callback.message.answer("⚠️ Не удалось отобразить идею.",
                                      disable_web_page_preview=True)
        print("Ошибка при отправке подробностей:", e)

    # --- учёт показов L1 и авто-микрофидбек
    try:
        supabase.table("seen_activities").upsert({
            "user_id": user_id,
            "activity_id": activity_id,
            "age_min": activity.get("age_min"),
            "age_max": activity.get("age_max"),
            "time_required": activity.get("time_required"),
            "energy": activity.get("energy"),
            "location": activity.get("location"),
            "level": "l1",
            "seen_at": datetime.now().isoformat()
        }).execute()

        ctx["l1_counter"] = int(ctx.get("l1_counter", 0)) + 1

        from handlers.feedback_activity import maybe_prompt_auto_feedback
        await maybe_prompt_auto_feedback(
            user_id=user_id,
            activity_id=activity_id,
            ctx=ctx,
            bot=callback.bot
        )
    except Exception as e:
        print(f"[microfeedback] trigger error: {e}")

    amplitude_log_event(
        user_id=user_id,
        event_name="show_activity_L1",
        event_properties={
            "activity_id": activity_id,
            "age_min": activity.get("age_min"),
            "age_max": activity.get("age_max"),
            "time_required": activity.get("time_required"),
            "energy": activity.get("energy"),
            "location": activity.get("location")
        },
        session_id=session_id
    )
    await callback.answer()


# --- кнопка “Покажи еще идею”
@activities_router.callback_query(F.data == "activity_next")
async def show_next_activity(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)

    # PAYWALL: если превышен лимит L0 (15)
    if should_block_l0(user_id):
        await send_universal_paywall(callback, reason="l0_limit", user_id=user_id, session_id=session_id)
        return

    activity_id, was_reset = get_next_activity_with_filters(
        user_id=user_id,
        age_min=int(ctx["age_min"]),
        age_max=int(ctx["age_max"]),
        time_required=ctx["time_required"],
        energy=ctx["energy"],
        location=ctx["location"]
    )

    if activity_id is None:
        await callback.message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.",
                                      disable_web_page_preview=True)
        return

    activity = get_activity_by_id(activity_id)
    if not activity:
        await callback.message.answer("😔 Больше идей нет для этих условий.",
                                      disable_web_page_preview=True)
        await callback.answer()
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Расскажи как играть",
                              callback_data=f"activity_details:{activity['id']}")],
        [InlineKeyboardButton(text="Покажи еще идею", callback_data="activity_next")],
        [InlineKeyboardButton(text="Хочу другие фильтры",
                              callback_data="update_filters")]
    ])

    image_url = activity.get("image_url")
    if image_url and image_url.strip():
        await callback.message.answer_photo(photo=image_url, caption=text,
                                            parse_mode="Markdown", reply_markup=keyboard,
                                            disable_web_page_preview=True)
    else:
        await callback.message.answer(text, parse_mode="Markdown",
                                      reply_markup=keyboard,
                                      disable_web_page_preview=True)
    amplitude_log_event(
        user_id=user_id,
        event_name="show_activity_L0",
        event_properties={
            "activity_id": activity["id"],
            "age_min": ctx["age_min"],
            "age_max": ctx["age_max"],
            "time_required": ctx["time_required"],
            "energy": ctx["energy"],
            "location": ctx["location"]
        },
        session_id=session_id
    )
    
    supabase.table("seen_activities").upsert({
        "user_id": user_id,
        "activity_id": activity["id"],
        "age_min": ctx["age_min"],
        "age_max": ctx["age_max"],
        "time_required": ctx["time_required"],
        "energy": ctx["energy"],
        "location": ctx["location"],
        "level": "l0",
        "seen_at": datetime.now().isoformat()
    }).execute()

    await callback.answer()


# --- /next команда (аналог show_next_activity)
@activities_router.message(Command("next"))
async def next_command_handler(message: types.Message):
    user_id = message.from_user.id
    ctx = ensure_filters(user_id)
    session_id = ctx.get("session_id") or get_current_session_id(user_id)

    # PAYWALL: если превышен лимит L0
    if should_block_l0(user_id):
        await send_universal_paywall(message, reason="l0_limit", user_id=user_id, session_id=session_id)
        return

    activity_id, was_reset = get_next_activity_with_filters(
        user_id=user_id,
        age_min=int(ctx["age_min"]),
        age_max=int(ctx["age_max"]),
        time_required=ctx["time_required"],
        energy=ctx["energy"],
        location=ctx["location"]
    )

    if activity_id is None:
        await message.answer("😔 Нет идей для таких условий, попробуйте изменить фильтры.",
                             disable_web_page_preview=True)
        return

    activity = get_activity_by_id(activity_id)
    if not activity:
        await message.answer("😔 Больше идей нет для этих условий.",
                             disable_web_page_preview=True)
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
        [InlineKeyboardButton(text="Хочу другие фильтры",
                              callback_data="update_filters")]
    ])

    image_url = activity.get("image_url")
    if image_url and image_url.strip():
        await message.answer_photo(photo=image_url, caption=text,
                                   parse_mode="Markdown", reply_markup=keyboard,
                                   disable_web_page_preview=True)
    else:
        await message.answer(text, parse_mode="Markdown",
                             reply_markup=keyboard,
                             disable_web_page_preview=True)

    amplitude_log_event(
        user_id=user_id,
        event_name="show_activity_L0_next_command",
        event_properties={
            "activity_id": activity["id"],
            "age_min": ctx["age_min"],
            "age_max": ctx["age_max"],
            "time_required": ctx["time_required"],
            "energy": ctx["energy"],
            "location": ctx["location"]
        },
        session_id=session_id
    )
    
    supabase.table("seen_activities").upsert({
        "user_id": user_id,
        "activity_id": activity["id"],
        "age_min": ctx["age_min"],
        "age_max": ctx["age_max"],
        "time_required": ctx["time_required"],
        "energy": ctx["energy"],
        "location": ctx["location"],
        "level": "l0",
        "seen_at": datetime.now().isoformat()
    }).execute()
