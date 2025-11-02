from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db.feedback_repository import save_feedback
from db.feature_flags import is_enabled, get_microfeedback_config
from db.user_status import is_premium_user
from utils.amplitude_logger import log_event
from handlers.user_state import user_data
from db.supabase_client import supabase

feedback_router = Router()


# --- Клавиатура фидбека (1 кнопка в строке)
def build_feedback_keyboard(activity_id: int, source: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="😍 Супер", callback_data=f"feedback:{activity_id}:super:{source}")],
        [InlineKeyboardButton(text="🙂 Норм", callback_data=f"feedback:{activity_id}:ok:{source}")],
        [InlineKeyboardButton(text="😕 Не зашло", callback_data=f"feedback:{activity_id}:bad:{source}")],
        [InlineKeyboardButton(text="💬 Написать текстом", callback_data=f"feedback_text:{activity_id}:{source}")]
    ])


# --- Команда или кнопка “Оставить отзыв”
@feedback_router.callback_query(F.data.startswith("feedback_button:"))
async def ask_manual_feedback(callback: types.CallbackQuery):
    if not is_enabled("ask_feedback_button_enabled"):
        await callback.answer()
        return

    activity_id = int(callback.data.split(":")[1])
    keyboard = build_feedback_keyboard(activity_id, source="manual_button")
    await callback.message.answer("💭 Поделитесь, как вам эта идея?", reply_markup=keyboard)
    await callback.answer()


# --- Функция: получаем фильтры и session_id с fallback
def get_filters_and_session(user_id: int):
    filters = user_data.get(user_id)
    if not filters:
        response = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
        if response.data:
            filters = response.data[0]
            user_data[user_id] = filters
    session_id = filters.get("session_id") if filters else None
    return filters, session_id


# --- Реакция на выбор оценки
@feedback_router.callback_query(F.data.startswith("feedback:"))
async def handle_feedback(callback: types.CallbackQuery):
    try:
        _, activity_id_str, rating, source = callback.data.split(":")
        activity_id = int(activity_id_str)
        user_id = callback.from_user.id
        is_premium = is_premium_user(user_id)

        filters, session_id = get_filters_and_session(user_id)

        save_feedback(
            user_id=user_id,
            activity_id=activity_id,
            rating=rating,
            source=source,
            paywall_user=is_premium,
            filters=filters,
            optional_comment=None,
            session_id=session_id,
            upsert=True  # 💾 теперь перезаписываем, если уже есть запись
        )

        log_event(user_id, "feedback_activity", {
            "activity_id": activity_id,
            "rating": rating,
            "source": source
        }, session_id=session_id)

        text_map = {
            "super": "Спасибо! 💚 Очень рады, что идея зашла!",
            "ok": "Спасибо за отзыв! 🙌 Мы постараемся сделать ещё лучше.",
            "bad": "Поняли 😔 Если есть идея, как улучшить — напишите.",
        }
        await callback.message.answer(text_map.get(rating, "Спасибо за фидбек!"))

        # 💬 Если юзер нажал "не зашло" — ждём текст
        if rating == "bad":
            user_data.setdefault(user_id, {})["awaiting_feedback_text"] = {
                "activity_id": activity_id,
                "source": source,
                "rating": "bad"
            }

        await callback.answer()

    except Exception as e:
        print("[feedback] Ошибка при обработке фидбека:", e)
        await callback.answer("⚠️ Что-то пошло не так", show_alert=True)


# --- Запрос текстового комментария (по кнопке)
@feedback_router.callback_query(F.data.startswith("feedback_text:"))
async def ask_text_feedback(callback: types.CallbackQuery):
    try:
        _, activity_id_str, source = callback.data.split(":")
        activity_id = int(activity_id_str)
        await callback.message.answer("✍️ Напишите, пожалуйста, ваш комментарий:")
        await callback.answer()

        # создаём user_data если его нет
        user_data.setdefault(callback.from_user.id, {})
        user_data[callback.from_user.id]["awaiting_feedback_text"] = {
            "activity_id": activity_id,
            "source": source
        }
    except Exception as e:
        print("[feedback] Ошибка при запросе текстового фидбека:", e)
        await callback.answer("⚠️ Что-то пошло не так", show_alert=True)


# --- Приём текстового комментария (в ответ на “не зашло” или “написать текстом”)
@feedback_router.message(F.text)
async def handle_text_feedback(message: types.Message):
    context = user_data.get(message.from_user.id, {}).get("awaiting_feedback_text")
    if not context:
        return  # не ждём текста

    user_id = message.from_user.id
    activity_id = context["activity_id"]
    source = context["source"]
    rating = context.get("rating", "text")

    is_premium = is_premium_user(user_id)
    filters, session_id = get_filters_and_session(user_id)

    save_feedback(
        user_id=user_id,
        activity_id=activity_id,
        rating=rating,
        source=source,
        paywall_user=is_premium,
        filters=filters,
        optional_comment=message.text,
        session_id=session_id,
        upsert=True
    )

    log_event(user_id, "feedback_text", {
        "activity_id": activity_id,
        "comment": message.text,
        "source": source,
        "rating": rating
    }, session_id=session_id)

    await message.answer("Спасибо 💚 Ваше сообщение сохранено!")
    user_data[message.from_user.id].pop("awaiting_feedback_text", None)
