from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from keyboards.common import start_inline_keyboard
from keyboards.onboarding import age_keyboard, time_keyboard, energy_keyboard, place_keyboard
from db.supabase_client import get_activity, supabase, ENERGY_MAP, TIME_MAP, PLACE_MAP
from utils.amplitude_logger import log_event, set_user_properties
from uuid import uuid4

router = Router()
user_data = {}


@router.message(CommandStart())
async def cmd_start(message: types.Message):
    log_event(user_id=message.from_user.id,
              event_name="start_bot",
              event_properties={"source": "telegram"})

    text = ("Привет, я бот *Близкие Игры*! 🤗\n\n"
            "Помогаю находить идеи, как провести время с детьми так, "
            "чтобы всем было тепло, весело и немного волшебно ✨")
    await message.answer(text,
                         parse_mode="Markdown",
                         reply_markup=start_inline_keyboard)


