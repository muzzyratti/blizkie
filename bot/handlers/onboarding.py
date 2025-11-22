from aiogram import Router, types, F
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, location_keyboard
from utils.amplitude_logger import log_event, set_user_properties
from utils.session import ensure_filters  # ✅ централизовано
from .user_state import user_data
from .activities import send_activity, show_next_activity
from db.supabase_client import supabase

onboarding_router = Router()


@onboarding_router.callback_query(F.data == "start_onboarding")
async def start_onboarding(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    ctx["mode"] = "onboarding"

    log_event(user_id, "onboarding_started", session_id=ctx["session_id"])

    await callback.message.answer(
        "Сколько лет вашему ребёнку?\n\n"
        "Если их несколько — ориентируемся на младшего.",
        reply_markup=age_keyboard)
    await callback.answer()


@onboarding_router.callback_query(F.data.startswith("age_"))
async def process_age(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    username = callback.from_user.username
    age_data = callback.data.replace("age_", "")

    if age_data == "3_4":
        age_min, age_max = 3, 4
    elif age_data == "5_6":
        age_min, age_max = 5, 6
    elif age_data == "7_8":
        age_min, age_max = 7, 8
    elif age_data == "9_10":
        age_min, age_max = 9, 10
    else:
        age_min = age_max = 0

    ctx["age_min"] = age_min
    ctx["age_max"] = age_max

    log_event(user_id, "set_age", {"age_min": age_min, "age_max": age_max}, session_id=ctx["session_id"])
    set_user_properties(user_id, {"age_min": age_min, "age_max": age_max})

    mode = ctx.get("mode")
    if mode == "onboarding":
        await callback.message.answer(
            f"Отлично! 🙌\n\n"
            "Сколько у тебя есть времени?\n\n"
            "Даже 10-15 минут — это уже волшебство ✨",
            reply_markup=time_keyboard)
    elif mode == "update":
        await callback.message.answer("Возраст обновлён. Вот идея для вас 👇")
        await show_next_activity(callback)
        supabase.table("user_filters").update({
            "username": username,
            "age_min": age_min,
            "age_max": age_max
        }).eq("user_id", user_id).execute()

    await callback.answer()


@onboarding_router.callback_query(F.data.startswith("time_"))
async def process_time(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    username = callback.from_user.username
    time_choice = callback.data.split("_")[1]

    ctx["time_required"] = time_choice

    log_event(user_id, "set_time", {"time_required": time_choice}, session_id=ctx["session_id"])
    set_user_properties(user_id, {"time_required": time_choice})

    mode = ctx.get("mode")
    if mode == "onboarding":
        await callback.message.answer(
            "Теперь про самое честное 😌\n\n"
            "Сколько у тебя сегодня сил?\n\n"
            "Тут нет правильных ответов — я подстроюсь ❤️",
            reply_markup=energy_keyboard)
    elif mode == "update":
        await callback.message.answer("Время обновлено. Вот идея для вас 👇")
        await show_next_activity(callback)
        supabase.table("user_filters").update({
            "username": username,
            "time_required": time_choice
        }).eq("user_id", user_id).execute()

    await callback.answer()


@onboarding_router.callback_query(F.data.startswith("energy_"))
async def process_energy(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    username = callback.from_user.username
    energy_choice = callback.data.split("_")[1]

    ctx["energy"] = energy_choice

    log_event(user_id, "set_energy", {"energy": energy_choice}, session_id=ctx["session_id"])
    set_user_properties(user_id, {"energy": energy_choice})

    mode = ctx.get("mode")
    if mode == "onboarding":
        await callback.message.answer(
            "Где вы планируете провести время? 🌿\n\n"
            "Дома? На улице? — я подберу идеи под ситуацию.",
            reply_markup=location_keyboard)
    elif mode == "update":
        await callback.message.answer("Энергия обновлена. Вот идея для вас 👇")
        await show_next_activity(callback)
        supabase.table("user_filters").update({
            "username": username,
            "energy": energy_choice
        }).eq("user_id", user_id).execute()

    await callback.answer()


@onboarding_router.callback_query(F.data.startswith("location_"))
async def process_location(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)
    username = callback.from_user.username
    location_choice = callback.data.split("_")[1]

    ctx["location"] = location_choice

    log_event(user_id, "set_location", {"location": location_choice}, session_id=ctx["session_id"])
    set_user_properties(user_id, {"location": location_choice})

    mode = ctx.get("mode")
    if mode == "onboarding":
        log_event(user_id, "onboarding_completed", session_id=ctx["session_id"])

        supabase.table("user_filters").upsert({
            "user_id": user_id,
            "username": username,
            "age_min": ctx["age_min"],
            "age_max": ctx["age_max"],
            "time_required": ctx["time_required"],
            "energy": ctx["energy"],
            "location": ctx["location"]
        }).execute()

        await callback.message.answer(
            "Класс! Всё настроили 🎉\n\n"
            "Подбираю идею для вас…"
        )

        await send_activity(callback)
    elif mode == "update":
        await callback.message.answer("Место обновлено. Вот идея для вас 👇")
        await show_next_activity(callback)
        supabase.table("user_filters").update({
            "username": username,
            "location": location_choice
        }).eq("user_id", user_id).execute()

    await callback.answer()


@onboarding_router.callback_query(F.data == "continue_with_filters")
async def continue_with_saved_filters(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    ctx = ensure_filters(user_id)

    response = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
    filters = response.data[0] if response.data else None

    if not filters:
        await callback.message.answer("Не удалось найти сохранённые фильтры 😔 Попробуйте начать заново.")
        await callback.answer()
        return

    # Обновляем фильтры в памяти
    ctx.update({
        "age_min": filters["age_min"],
        "age_max": filters["age_max"],
        "time_required": filters["time_required"],
        "energy": filters["energy"],
        "location": filters["location"],
        "mode": "onboarding"
    })

    await callback.answer("Показываю идеи по вашему выбору 👇")
    await send_activity(callback)
