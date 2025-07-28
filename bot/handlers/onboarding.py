from aiogram import Router, types, F
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, place_keyboard
from utils.amplitude_logger import log_event, set_user_properties
from .user_state import user_data
from .activities import send_activity, show_next_activity

onboarding_router = Router()


@onboarding_router.callback_query(F.data == "start_onboarding")
async def start_onboarding(callback: types.CallbackQuery):
  user_id = callback.from_user.id
  user_data[user_id] = {"mode": "onboarding"}

  log_event(user_id, "onboarding_started")

  await callback.message.answer(
      "Сколько лет вашему ребёнку? (если их несколько, выбирайте младшего):",
      reply_markup=age_keyboard)
  await callback.answer()


@onboarding_router.callback_query(F.data.startswith("age_"))
async def process_age(callback: types.CallbackQuery):
  age = int(callback.data.split("_")[1])
  user_id = callback.from_user.id
  user_data.setdefault(user_id, {})["age"] = age

  log_event(user_id, "set_age", {"age": age})
  set_user_properties(user_id, {"age": age})

  mode = user_data[user_id].get("mode")
  if mode == "onboarding":
    await callback.message.answer(
        f"Вы выбрали возраст ребёнка: {age} лет.\n\n"
        "Сколько у вас есть времени на активность?",
        reply_markup=time_keyboard)
  elif mode == "update":
    await callback.message.answer("Возраст обновлён. Вот идея для вас 👇")
    await show_next_activity(callback)

  await callback.answer()


@onboarding_router.callback_query(F.data.startswith("time_"))
async def process_time(callback: types.CallbackQuery):
  time_choice = callback.data.split("_")[1]
  user_id = callback.from_user.id
  user_data[user_id]["time"] = time_choice

  log_event(user_id, "set_time", {"time": time_choice})
  set_user_properties(user_id, {"time": time_choice})

  mode = user_data[user_id].get("mode")
  if mode == "onboarding":
    await callback.message.answer(
        "Сколько у вас сегодня энергии на игру? (честно 😌)",
        reply_markup=energy_keyboard)
  elif mode == "update":
    await callback.message.answer("Время обновлено. Вот идея для вас 👇")
    await show_next_activity(callback)
  await callback.answer()


@onboarding_router.callback_query(F.data.startswith("energy_"))
async def process_energy(callback: types.CallbackQuery):
  energy_choice = callback.data.split("_")[1]
  user_id = callback.from_user.id
  user_data[user_id]["energy"] = energy_choice

  log_event(user_id, "set_energy", {"energy": energy_choice})
  set_user_properties(user_id, {"energy": energy_choice})

  mode = user_data[user_id].get("mode")
  if mode == "onboarding":
    await callback.message.answer("Где будете проводить время?",
                                  reply_markup=place_keyboard)
  elif mode == "update":
    await callback.message.answer("Энергия обновлена. Вот идея для вас 👇")
    await show_next_activity(callback)
  await callback.answer()


@onboarding_router.callback_query(F.data.startswith("place_"))
async def process_place(callback: types.CallbackQuery):
  place_choice = callback.data.split("_")[1]
  user_id = callback.from_user.id
  user_data[user_id]["place"] = place_choice

  log_event(user_id, "set_place", {"place": place_choice})
  set_user_properties(user_id, {"place": place_choice})

  mode = user_data[user_id].get("mode")
  if mode == "onboarding":
    log_event(user_id, "onboarding_completed")
    await send_activity(callback)
  elif mode == "update":
    await callback.message.answer("Место обновлено. Вот идея для вас 👇")
    await show_next_activity(callback)
  await callback.answer()
