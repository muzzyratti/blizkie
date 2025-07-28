from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from aiogram import Bot
from db.supabase_client import supabase
import pytz

REMINDER_TEXT = "Время на близость. Одна игра — много любви 💛"
TIMEZONE = pytz.timezone("Europe/Moscow")


def setup_reminder_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Отправка по средам и пятницам в 18:40
    trigger = CronTrigger(day_of_week="wed,fri", hour=18, minute=40)

    @scheduler.scheduled_job(trigger)
    async def send_reminders():
        print("[REMINDER] Рассылка началась...")

        now = datetime.now(TIMEZONE)
        yesterday = now - timedelta(hours=24)

        # Получаем всех, кто запускал бота и заполнил фильтры
        response = supabase.table("user_sessions").select("*").execute()
        users = response.data or []

        for user in users:
            user_id = user.get("user_id")
            last_seen = user.get("last_seen_at")
            has_filters = all([
                user.get("age"),
                user.get("time"),
                user.get("energy"),
                user.get("place")
            ])

            if not has_filters:
                continue

            # Если never seen — рассылаем
            if not last_seen:
                should_send = True
            else:
                try:
                    seen_at = datetime.fromisoformat(last_seen)
                    should_send = seen_at < yesterday
                except Exception:
                    should_send = True

            if should_send:
                try:
                    await bot.send_message(chat_id=user_id, text=REMINDER_TEXT)
                    # Обновляем last_seen_at
                    supabase.table("user_sessions").update({
                        "last_seen_at":
                        now.isoformat()
                    }).eq("user_id", user_id).execute()
                    print(f"[REMINDER] Отправлено: {user_id}")
                except Exception as e:
                    print(f"[REMINDER] Ошибка при отправке {user_id}: {e}")

        print("[REMINDER] Рассылка завершена.")


async def send_reminders_now(bot: Bot):
    print("[REMINDER] Ручной запуск рассылки")
    try:
        now = datetime.now(tz=ZoneInfo("Europe/Moscow"))
        print(f"[REMINDER] Сейчас {now}")

        response = supabase.table("user_sessions").select("*").execute()
        users = response.data or []

        count = 0
        for user in users:
            user_id = user.get("user_id")
            filters = {
                "age": user.get("age"),
                "time": user.get("time"),
                "energy": user.get("energy"),
                "place": user.get("place")
            }

            if not all(filters.values()):
                continue

            last_seen = user.get("last_seen_at")
            if last_seen:
                last_seen_dt = datetime.fromisoformat(last_seen)
                delta = now - last_seen_dt
                if delta.total_seconds() < 60 * 60 * 24:  # меньше суток назад
                    continue

            try:
                await bot.send_message(chat_id=user_id, text=REMINDER_TEXT)
                count += 1
            except Exception as e:
                print(f"[REMINDER] Не удалось отправить {user_id}: {e}")
        print(f"[REMINDER] Рассылка завершена. Отправлено: {count}")
    except Exception as e:
        print(f"[REMINDER] Ошибка при ручной рассылке: {e}")
