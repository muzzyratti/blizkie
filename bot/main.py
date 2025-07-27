import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN
from utils.logger import setup_logger
from handlers import start
from handlers.favorites import favorites_router
from handlers.update_filters import update_filters_router

logger = setup_logger()

async def set_bot_commands(bot):
    commands = [
        BotCommand(command="start", description="Начать"),
        BotCommand(command="favorites", description="Мои любимые"),
        BotCommand(command="update_filters", description="Хочу другие советы"),
    ]
    await bot.set_my_commands(commands)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(favorites_router)
    dp.include_router(update_filters_router)

    logger.info("Устанавливаем команды бота...")
    await set_bot_commands(bot)

    logger.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
