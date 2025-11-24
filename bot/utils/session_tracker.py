# utils/session_tracker.py
import asyncio
from datetime import datetime, timedelta, timezone
from db.supabase_client import supabase
from handlers.user_state import user_data
from utils.logger import setup_logger
from utils.push_scheduler import (
    schedule_retention_nudges,
    schedule_paywall_followup,
    schedule_retention_nudges_subscribers,
    schedule_interview_invite,
)
from utils.paywall_guard import is_user_limited, is_premium
from db.feature_flags import get_flag  # 👈 добавили импорт

logger = setup_logger()

# ============================================================
#   ДЕФОЛТЫ НА СЛУЧАЙ, ЕСЛИ feature_flags НЕДОСТУПЕН
#   (прод: 30 мин и 180 сек, как ты просил)
# ============================================================
SESSION_TIMEOUT_MINUTES = 30
SYNC_INTERVAL_SECONDS = 180

# ключ в feature_flags
_SESSION_CFG_KEY = "session_tracker_config"


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    if not dt:
        return None
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


# ============================================================
#  ЗАГРУЗКА НАСТРОЕК ИЗ feature_flags
#  value_json ожидаем такого вида:
#
#  {
#    "SESSION_TIMEOUT_MINUTES": 30,
#    "SYNC_INTERVAL_SECONDS": 180,
#    "per_user": {
#      "276358220": {
#        "SESSION_TIMEOUT_MINUTES": 1
#      }
#    }
#  }
# ============================================================

def _get_session_config() -> dict:
    """
    Тянем конфиг трекинга сессий из feature_flags.
    Если что-то не так — возвращаем {} и работаем на дефолтах.
    """
    try:
        cfg = get_flag(_SESSION_CFG_KEY, default={})
        if not isinstance(cfg, dict):
            return {}
        return cfg
    except Exception as e:
        logger.warning(f"[session_tracker] ⚠️ feature_flags error: {e}")
        return {}


def _get_session_timeout_for_user(user_id: int | None) -> int:
    """
    Возвращает таймаут сессии в минутах.
    1) Берём общий SESSION_TIMEOUT_MINUTES из config или дефолта.
    2) Если есть per_user-override для этого user_id — используем его.
    """
    cfg = _get_session_config()
    default_timeout = cfg.get("SESSION_TIMEOUT_MINUTES", SESSION_TIMEOUT_MINUTES)

    try:
        default_timeout = int(default_timeout)
    except (TypeError, ValueError):
        default_timeout = SESSION_TIMEOUT_MINUTES

    if user_id is None:
        return default_timeout

    per_user = cfg.get("per_user") or {}
    # user_id может быть строкой или числом в JSON, подстрахуемся
    user_cfg = (
        per_user.get(str(user_id))
        or per_user.get(user_id)
    )

    if isinstance(user_cfg, dict) and "SESSION_TIMEOUT_MINUTES" in user_cfg:
        try:
            return int(user_cfg["SESSION_TIMEOUT_MINUTES"])
        except (TypeError, ValueError):
            pass

    return default_timeout


def _get_sync_interval() -> int:
    """
    Интервал синка в секундах.
    Общий (глобальный), но берётся через feature_flags.
    """
    cfg = _get_session_config()
    value = cfg.get("SYNC_INTERVAL_SECONDS", SYNC_INTERVAL_SECONDS)
    try:
        return int(value)
    except (TypeError, ValueError):
        return SYNC_INTERVAL_SECONDS


def get_current_session_id(user_id: int) -> str | None:
    ctx = user_data.get(user_id)
    return ctx.get("session_id") if ctx else None


def touch_user_activity(
    user_id: int,
    *,
    source: str | None = None,
    device_info: dict | None = None,
    username: str | None = None,
):
    now = _utcnow()
    ctx = user_data.setdefault(user_id, {})

    # 👇 сохраняем последний известный username, если он есть
    if username is not None:
        ctx["username"] = username

    # Нормализация
    for key in ("created_at", "last_seen"):
        v = ctx.get(key)
        if isinstance(v, datetime) and v.tzinfo is None:
            ctx[key] = v.replace(tzinfo=timezone.utc)

    sid = ctx.get("session_id")
    ended = ctx.get("marked_ended", False)

    # ✅ 1. Если есть активная сессия и timeout НЕ истёк — просто обновляем
    if sid and not ended:
        last_seen = ctx.get("last_seen") or now
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)

        timeout_minutes = _get_session_timeout_for_user(user_id)
        if (now - last_seen) <= timedelta(minutes=timeout_minutes):
            ctx["last_seen"] = now
            ctx["last_event"] = "activity"
            ctx["actions_count"] = int(ctx.get("actions_count", 0)) + 1
            if source:
                ctx["source"] = source
            if device_info is not None:
                ctx["device_info"] = device_info
            return  # ✅ НИКАКОГО создания новой сессии

    # ✅ 2. Если тут — старая сессия закрыта ИЛИ её не было → создаём новую
    sid = f"{user_id}_{now.strftime('%Y%m%d_%H%M%S')}"
    ctx["session_id"] = sid
    ctx["created_at"] = now
    ctx["last_seen"] = now
    ctx["first_event"] = ctx.get("first_event") or "start_bot"
    ctx["last_event"] = "activity"
    ctx["actions_count"] = 0
    ctx["marked_ended"] = False

    if source:
        ctx["source"] = source
    if device_info is not None:
        ctx["device_info"] = device_info

    try:
        (
            supabase.table("push_queue")
            .delete()
            .eq("user_id", user_id)
            .eq("status", "pending")
            .neq("type", "premium_ritual")
            .execute()
        )

        logger.info(f"[session] 🧹 Cleared pending pushes except premium_ritual user={user_id}")
    except Exception as e:
        logger.warning(f"[session] ⚠️ Clear pending pushes failed user={user_id}: {e}")

    logger.info(f"[session] 🆕 New session created for user={user_id}")


def mark_seen(
    user_id: int,
    *,
    source: str | None = None,
    device_info: dict | None = None,
    username: str | None = None,
):
    return touch_user_activity(
        user_id,
        source=source,
        device_info=device_info,
        username=username,
    )


def new_session_if_needed(
    user_id: int,
    *,
    source: str | None = None,
    device_info: dict | None = None,
    username: str | None = None,
):
    return touch_user_activity(
        user_id,
        source=source,
        device_info=device_info,
        username=username,
    )


async def sync_sessions_to_db():
    while True:
        try:
            now = _utcnow()
            active_count = 0
            closed_count = 0

            for user_id, ctx in list(user_data.items()):
                sid = ctx.get("session_id")
                if not sid:
                    continue

                created_at = ctx.get("created_at") or now
                last_seen = ctx.get("last_seen") or created_at

                # safety: приводим к aware
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                if last_seen.tzinfo is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)

                timeout_minutes = _get_session_timeout_for_user(user_id)
                inactive = (now - last_seen) > timedelta(minutes=timeout_minutes)
                ended_at = last_seen if inactive else None

                if inactive:
                    closed_count += 1
                else:
                    active_count += 1

                filters = {
                    k: ctx.get(k)
                    for k in ("age_min", "age_max", "time_required", "energy", "location")
                } or {}

                # favorites_count без тяжёлых агрегаций
                try:
                    fav_resp = (
                        supabase.table("favorites")
                        .select("activity_id")
                        .eq("user_id", user_id)
                        .execute()
                    )
                    unique_ids = {
                        row.get("activity_id")
                        for row in (fav_resp.data or [])
                        if row.get("activity_id")
                    }
                    favorites_count = len(unique_ids)
                except Exception as e:
                    logger.warning(f"[session_tracker] ⚠️ Favorites count error user={user_id}: {e}")
                    favorites_count = 0

                duration = int((last_seen - created_at).total_seconds())
                if duration < 0:
                    duration = 0

                session_data = {
                    "session_id": sid,
                    "user_id": user_id,
                    "username": ctx.get("username"),
                    "started_at": _iso(created_at),
                    "last_seen": _iso(last_seen),
                    "ended_at": _iso(ended_at),
                    "duration_seconds": duration,
                    "filters": filters,
                    "actions_count": int(ctx.get("actions_count", 0)),
                    "favorites_count": favorites_count,
                    "first_event": ctx.get("first_event"),
                    "last_event": ctx.get("last_event"),
                    "source": ctx.get("source"),
                    "device_info": ctx.get("device_info") or {},
                }

                # Если уже пометили закрытой — не триггерим повторно
                if inactive and ctx.get("marked_ended"):
                    supabase.table("user_sessions").upsert(session_data).execute()
                    continue

                # Апсерт в БД
                supabase.table("user_sessions").upsert(session_data).execute()

                if inactive:
                    try:
                        # 1) Бесплатный, который УПЁРСЯ в лимит → paywall follow-up
                        if is_user_limited(user_id):
                            reason = ctx.get("last_paywall_reason") or "session_end"
                            schedule_paywall_followup(user_id, reason=reason)
                            logger.info(f"[session_tracker] 📬 Paywall-followup scheduled for user={user_id}")

                        else:
                            # 2) Лимит НЕ достигнут — различаем премиум / не премиум
                            if is_premium(user_id):
                                # Новая редкая цепочка для подписчиков
                                schedule_retention_nudges_subscribers(user_id)
                                logger.info(
                                    f"[session_tracker] 📬 Retention-nudges SUBSCRIBERS scheduled for user={user_id}"
                                )
                                try:
                                    schedule_interview_invite(user_id)
                                except Exception as e:
                                    logger.error(
                                        f"[session_tracker] interview_invite error for user={user_id}: {e}"
                                    )
                            else:
                                # Бесплатный, который не достиг лимита
                                schedule_retention_nudges(user_id)
                                logger.info(
                                    f"[session_tracker] 📬 Retention-nudges scheduled for user={user_id}"
                                )

                    except Exception as e:
                        logger.warning(f"[session_tracker] ❌ Push schedule error user={user_id}: {e}")

                    ctx["marked_ended"] = True

            logger.info(
                f"[session_tracker] ✅ Synced sessions (active={active_count}, closed={closed_count})"
            )

        except Exception as e:
            logger.warning(f"[session_tracker] ❌ Sync error: {e}")

        interval = _get_sync_interval()
        await asyncio.sleep(interval)
