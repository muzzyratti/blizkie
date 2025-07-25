from aiogram import Router, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from keyboards.common import start_inline_keyboard
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, place_keyboard
from db.supabase_client import get_activity, supabase, ENERGY_MAP, TIME_MAP, PLACE_MAP

router = Router()
user_data = {}


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    text = ("Привет, я бот *Близкие Игры*! 🤗\n\n"
            "Помогаю находить идеи, как провести время с детьми так, "
            "чтобы всем было тепло, весело и немного волшебно ✨")
    await message.answer(text,
                         parse_mode="Markdown",
                         reply_markup=start_inline_keyboard)


@router.callback_query(F.data == "start_onboarding")
async def start_onboarding(callback: types.CallbackQuery):
    await callback.message.answer(
        "Сколько лет вашему ребёнку? (если их несколько, выбирайте младшего):",
        reply_markup=age_keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("age_"))
async def process_age(callback: types.CallbackQuery):
    age = int(callback.data.split("_")[1])
    user_data[callback.from_user.id] = {"age": age}
    await callback.message.answer(
        f"Вы выбрали возраст ребёнка: {age} лет.\n\n"
        "Сколько у вас есть времени на активность?",
        reply_markup=time_keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("time_"))
async def process_time(callback: types.CallbackQuery):
    time_choice = callback.data.split("_")[1]
    user_data[callback.from_user.id]["time"] = time_choice
    await callback.message.answer(
        "Сколько у вас сегодня энергии на игру? (честно 😌)",
        reply_markup=energy_keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("energy_"))
async def process_energy(callback: types.CallbackQuery):
    energy_choice = callback.data.split("_")[1]
    user_data[callback.from_user.id]["energy"] = energy_choice
    await callback.message.answer("Где будете проводить время?",
                                  reply_markup=place_keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("place_"))
async def process_place(callback: types.CallbackQuery):
    place_choice = callback.data.split("_")[1]
    user_data[callback.from_user.id]["place"] = place_choice

    filters = user_data[callback.from_user.id]
    activity = get_activity(age=int(filters["age"]),
                            time_required=filters["time"],
                            energy=filters["energy"],
                            location=filters["place"])

    if not activity:
        await callback.message.answer(
            "😔 Нет идей для таких условий, попробуйте изменить фильтры.")
        await callback.answer()
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="Расскажи как играть",
                callback_data=f"activity_details:{activity['id']}")
        ],
                         [
                             InlineKeyboardButton(
                                 text="Покажи еще идею",
                                 callback_data="activity_next")
                         ]])

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("activity_details:"))
async def show_activity_details(callback: types.CallbackQuery):
    activity_id = int(callback.data.split(":")[1])
    response = supabase.table("activities").select("*").eq(
        "id", activity_id).execute()
    if not response.data:
        await callback.message.answer(
            "😔 Не удалось найти подробности активности.")
        await callback.answer()
        return
    activity = response.data[0]

    summary = "\n".join([f"💡 {s}" for s in (activity['summary'] or [])])
    text = (
        f"🎲 *{activity['title']}*\n\n"
        f"⏱️ {activity['time_required']} • ⚡️ {activity['energy']} • 📍 {activity['location']}\n\n"
        f"Материалы: {activity['materials'] or 'Не требуются'}\n\n"
        f"{activity['full_description']}\n\n"
        f"{summary}")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Покажи еще идею",
                             callback_data="activity_next")
    ]])

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "activity_next")
async def show_next_activity(callback: types.CallbackQuery):
    filters = user_data.get(callback.from_user.id)
    if not filters:
        await callback.message.answer("Сначала пройдите подбор заново: /start")
        await callback.answer()
        return

    activity = get_activity(age=int(filters["age"]),
                            time_required=filters["time"],
                            energy=filters["energy"],
                            location=filters["place"])

    if not activity:
        await callback.message.answer("😔 Больше идей нет для этих условий.")
        await callback.answer()
        return

    text = (f"🎲 *{activity['title']}*\n\n"
            f"{activity['short_description']}\n\n"
            f"💡 {' • '.join(activity['summary'] or [])}\n\n"
            f"📦 Материалы: {activity['materials'] or 'Не требуются'}")

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="Расскажи как играть",
                callback_data=f"activity_details:{activity['id']}")
        ],
                         [
                             InlineKeyboardButton(
                                 text="Покажи еще идею",
                                 callback_data="activity_next")
                         ]])

    await callback.message.answer_photo(photo=activity["image_url"],
                                        caption=text,
                                        parse_mode="Markdown",
                                        reply_markup=keyboard)
    await callback.answer()
