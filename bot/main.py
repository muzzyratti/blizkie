import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from config import BOT_TOKEN
from utils.logger import setup_logger
from handlers import start
from handlers.onboarding import onboarding_router
from handlers.activities import activities_router
from handlers.favorites import favorites_router
from handlers.share import share_router
from handlers.update_filters import update_filters_router
from handlers.feedback import feedback_router
from handlers.feedback_activity import feedback_router as feedback_activity_router
from handlers.subscribe import subscribe_router
from handlers import donate
from utils.session_tracker import sync_sessions_to_db

logger = setup_logger()


async def set_bot_commands(bot):
    commands = [
        BotCommand(command="start", description="🚀 Начать заново"),
        BotCommand(command="next", description="🎲 Показать ещё идею"),
        BotCommand(command="favorites", description="❤️ Мои любимые идеи"),
        BotCommand(command="update_filters", description="🎛️ Хочу другие фильтры"),
        BotCommand(command="feedback", description="🧸 Поделиться мнением или ошибкой"),
        BotCommand(command="subscribe", description="📢 Подписаться на канал"),
        BotCommand(command="donate", description="💛 Поддержать проект"),
    ]
    await bot.set_my_commands(commands)


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)
    dp.include_router(onboarding_router)
    dp.include_router(activities_router)
    dp.include_router(favorites_router)
    dp.include_router(share_router)
    dp.include_router(update_filters_router)
    dp.include_router(feedback_router)
    dp.include_router(feedback_activity_router)
    dp.include_router(subscribe_router)
    dp.include_router(donate.router)

    logger.info("Устанавливаем команды бота...")
    await set_bot_commands(bot)

    logger.info("Бот запускается...")
    
    asyncio.create_task(sync_sessions_to_db())
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
