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
from handlers.donate import donate_router
from handlers.cancel_subscription import cancel_subscription_router
from handlers.paywall import paywall_router
from utils.session_tracker import sync_sessions_to_db
from workers.worker_pushes import run_worker
from middleware.activity_middleware import ActivityMiddleware
from handlers.suggest_game import suggest_router

# === ДОБАВЛЕНО: импорт для восстановления weekly пушей ===
from utils.push_scheduler import schedule_premium_ritual
from db.supabase_client import supabase

logger = setup_logger()


async def set_bot_commands(bot):
    commands = [
        BotCommand(command="start", description="🚀 Начать заново"),
        BotCommand(command="next", description="🎲 Показать ещё идею"),
        BotCommand(command="favorites", description="❤️ Мои любимые идеи"),
        BotCommand(command="update_filters", description="🎛️ Поменять фильтры"),
        BotCommand(command="suggest", description="🧩 Предложить свою игру"),
        BotCommand(command="feedback", description="❓ Рассказать об ошибке или предложении"),
        BotCommand(command="subscribe", description="📢 Подписаться на телеграм-канал"),
        BotCommand(command="donate", description="💛 Поддержать проект"),
        BotCommand(command="cancel_subscription", description="❌ Отменить подписку"),
    ]
    await bot.set_my_commands(commands)


# === ДОБАВЛЕНО: функция восстановления weekly пушей ===
async def restore_all_premium_rituals():
    """
    При запуске бота восстанавливаем weekly-пуши для всех активных подписчиков.
    schedule_premium_ritual сам удаляет старые pending и ставит новые.
    """
    try:
        rows = (
            supabase.table("user_subscriptions")
            .select("user_id, is_active")
            .eq("is_active", True)
            .execute()
        ).data or []

        for row in rows:
            uid = row["user_id"]
            try:
                schedule_premium_ritual(uid)
                logger.info(f"🔁 Restored weekly ritual for user={uid}")
            except Exception as e:
                logger.warning(f"❌ Failed restoring ritual for user={uid}: {e}")

    except Exception as e:
        logger.warning(f"❌ Failed to load active subscriptions: {e}")


async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.message.middleware(ActivityMiddleware())
    dp.callback_query.middleware(ActivityMiddleware())

    # --- подключаем все роутеры
    dp.include_router(start.router)
    dp.include_router(onboarding_router)
    dp.include_router(activities_router)
    dp.include_router(favorites_router)
    dp.include_router(share_router)
    dp.include_router(update_filters_router)
    dp.include_router(feedback_router)
    dp.include_router(suggest_router)
    dp.include_router(subscribe_router)
    dp.include_router(donate_router)
    dp.include_router(cancel_subscription_router)
    dp.include_router(paywall_router)
    dp.include_router(feedback_activity_router)
    

    logger.info("Устанавливаем команды бота...")
    await set_bot_commands(bot)

    logger.info("Бот запускается...")

    # === ДОБАВЛЕНО: восстановление weekly-пушей ===
    asyncio.create_task(restore_all_premium_rituals())

    asyncio.create_task(sync_sessions_to_db())
    asyncio.create_task(run_worker(bot))  # фоновый push-воркер

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
