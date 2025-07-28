from aiogram import Router, types, F
from utils.reminder_scheduler import send_reminders_now
import os

ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))

reminder_admin_router = Router()


@reminder_admin_router.message(F.text == "/send_reminder_test")
async def manual_reminder_trigger(message: types.Message):
    if message.from_user.id != ADMIN_USER_ID:
        await message.answer("⛔ Только для админа.")
        return

    await message.answer("🚀 Запускаю тестовую рассылку...")
    await send_reminders_now(message.bot)
    await message.answer("✅ Готово.")
