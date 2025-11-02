import asyncio
from datetime import datetime
from db.supabase_client import supabase
from handlers.user_state import user_data
from utils.logger import setup_logger

logger = setup_logger()

SESSION_TIMEOUT_MINUTES = 30
SYNC_INTERVAL_SECONDS = 120  # каждые 2 минуты


async def sync_sessions_to_db():
    """Периодически сохраняет активные сессии в Supabase."""
    while True:
        try:
            now = datetime.utcnow()

            for user_id, ctx in list(user_data.items()):
                sid = ctx.get("session_id")
                last_seen = ctx.get("last_seen", now)
                created_at = ctx.get("created_at", now)

                if not sid:
                    continue

                duration = int((now - created_at).total_seconds())
                filters = {
                    k: ctx.get(k)
                    for k in ("age_min", "age_max", "time_required", "energy", "location")
                }

                # корректный подсчёт favorites
                try:
                    fav_resp = supabase.table("favorites") \
                        .select("activity_id", count="exact") \
                        .eq("user_id", user_id) \
                        .execute()
                    unique_ids = {row["activity_id"] for row in (fav_resp.data or []) if row.get("activity_id")}
                    favorites_count = len(unique_ids)
                except Exception as e:
                    logger.warning(f"[session_tracker] ⚠️ Favorites count error for user={user_id}: {e}")
                    favorites_count = 0

                # собираем данные о сессии
                session_data = {
                    "session_id": sid,
                    "user_id": user_id,
                    "started_at": created_at.isoformat(),
                    "last_seen": last_seen.isoformat(),
                    "duration_seconds": duration,
                    "filters": filters or {},
                    "actions_count": ctx.get("actions_count", 0),
                    "favorites_count": favorites_count,
                    "first_event": ctx.get("first_event"),
                    "last_event": ctx.get("last_event"),
                    "source": ctx.get("source"),
                    "device_info": ctx.get("device_info") or {},
                }

                # записываем в базу
                supabase.table("user_sessions").upsert(session_data).execute()

            logger.info("[session_tracker] ✅ Synced all sessions to Supabase")

        except Exception as e:
            logger.warning(f"[session_tracker] ❌ Sync error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
