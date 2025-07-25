import asyncio
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN
from utils.logger import setup_logger
from handlers import start

logger = setup_logger()

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start.router)

    logger.info("Бот запускается...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
