import asyncio
from datetime import datetime, timedelta
from db.supabase_client import supabase
from handlers.user_state import user_data
from utils.logger import setup_logger

logger = setup_logger()

SESSION_TIMEOUT_MINUTES = 30
SYNC_INTERVAL_SECONDS = 120  # каждые 2 минуты


async def sync_sessions_to_db():
    """Периодически сохраняет активные сессии в Supabase."""
    timeout = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    while True:
        try:
            now = datetime.utcnow()
            active_count = 0
            closed_count = 0

            for user_id, ctx in list(user_data.items()):
                sid = ctx.get("session_id")
                last_seen = ctx.get("last_seen", now)
                created_at = ctx.get("created_at", now)

                if not sid:
                    continue

                # Проверяем, не "умерла" ли сессия
                inactive_timedelta = now - last_seen
                is_inactive = inactive_timedelta > timeout

                ended_at = None
                if is_inactive:
                    ended_at = last_seen
                    closed_count += 1
                else:
                    active_count += 1

                # считаем только длительность для активных
                duration = int((last_seen - created_at).total_seconds())

                filters = {
                    k: ctx.get(k)
                    for k in ("age_min", "age_max", "time_required", "energy", "location")
                }

                # корректный подсчёт favorites
                try:
                    fav_resp = (
                        supabase.table("favorites")
                        .select("activity_id", count="exact")
                        .eq("user_id", user_id)
                        .execute()
                    )
                    unique_ids = {
                        row["activity_id"]
                        for row in (fav_resp.data or [])
                        if row.get("activity_id")
                    }
                    favorites_count = len(unique_ids)
                except Exception as e:
                    logger.warning(
                        f"[session_tracker] ⚠️ Favorites count error for user={user_id}: {e}"
                    )
                    favorites_count = 0

                session_data = {
                    "session_id": sid,
                    "user_id": user_id,
                    "started_at": created_at.isoformat(),
                    "last_seen": last_seen.isoformat(),
                    "ended_at": ended_at.isoformat() if ended_at else None,
                    "duration_seconds": duration,
                    "filters": filters or {},
                    "actions_count": ctx.get("actions_count", 0),
                    "favorites_count": favorites_count,
                    "first_event": ctx.get("first_event"),
                    "last_event": ctx.get("last_event"),
                    "source": ctx.get("source"),
                    "device_info": ctx.get("device_info") or {},
                }

                # если сессия завершена — апдейтим только один раз
                if is_inactive and ctx.get("marked_ended"):
                    continue  # уже закрыта, не трогаем больше

                supabase.table("user_sessions").upsert(session_data).execute()

                if is_inactive:
                    ctx["marked_ended"] = True  # чтобы не апдейтить больше

            logger.info(
                f"[session_tracker] ✅ Synced sessions (active={active_count}, closed={closed_count})"
            )

        except Exception as e:
            logger.warning(f"[session_tracker] ❌ Sync error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
