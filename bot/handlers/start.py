from aiogram import Router, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.common import start_inline_keyboard
from db.supabase_client import supabase, ENERGY_MAP, TIME_MAP, PLACE_MAP
from utils.amplitude_logger import log_event
from handlers.user_state import user_data

router = Router()


@router.message(CommandStart())
async def cmd_start(message: types.Message):
          user_id = message.from_user.id

          log_event(user_id=user_id,
                    event_name="start_bot",
                    event_properties={"source": "telegram"})

          # Проверяем, есть ли сохранённые фильтры
          response = supabase.table("user_filters").select("*").eq(
              "user_id", user_id).execute()
          filters = response.data[0] if response.data else None

          if filters:
                    # Формируем текст с текущими фильтрами
                    time_label = TIME_MAP.get(filters["time"], filters["time"])
                    energy_label = ENERGY_MAP.get(filters["energy"],
                                                  filters["energy"])
                    place_label = PLACE_MAP.get(filters.get("location"),
                                                filters.get("location", "не указано"))

                    text = (
                        "Привет! ✨\n\n"
                        "Ваши текущие фильтры:\n"
                        f"👶 Возраст: {filters['age']} лет\n"
                        f"⏳ Время: {time_label}\n"
                        f"⚡️ Энергия: {energy_label}\n"
                        f"📍 Место: {place_label}\n\n"
                        "Хотите продолжить с этими фильтрами или выбрать заново?"
                    )

                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔄 Хочу новые фильтры",
                                callback_data="start_onboarding")
                        ],
                        [
                            InlineKeyboardButton(
                                text="▶️ Продолжить с этими",
                                callback_data="continue_with_filters")
                        ]
                    ])

                    await message.answer(text, reply_markup=keyboard)
          else:
                    # Стартовое приветствие, если пользователь запускает в первый раз
                    text = (
                        "Привет, я бот *Близкие Игры*! 🤗\n\n"
                        "Помогаю находить идеи, как провести время с детьми так, "
                        "чтобы всем было тепло, весело и немного волшебно ✨")

                    await message.answer(text,
                                         parse_mode="Markdown",
                                         reply_markup=start_inline_keyboard)
