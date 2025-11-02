import uuid
from datetime import datetime, timedelta
from db.supabase_client import supabase
from handlers.user_state import user_data
from utils.logger import setup_logger

logger = setup_logger()

SESSION_TIMEOUT_MINUTES = 30  # сколько минут неактивности до новой сессии


def _make_new_session_id(user_id: int) -> str:
    """Создаёт уникальный session_id для аналитики."""
    return f"{user_id}_{datetime.utcnow().strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"


def ensure_user_context(user_id: int) -> dict:
    """
    Гарантирует, что для user_id есть контекст в памяти (user_data[user_id]).
    Если session_id отсутствует или сессия устарела (>30 мин), создаёт новый.
    """
    if user_id not in user_data:
        user_data[user_id] = {}

    ctx = user_data[user_id]
    now = datetime.utcnow()

    last_seen = ctx.get("last_seen")
    session_id = ctx.get("session_id")

    # если нет session_id — создаём первый
    if not session_id:
        ctx["session_id"] = _make_new_session_id(user_id)
        ctx["created_at"] = now
        ctx["actions_count"] = 0
        ctx["first_event"] = None
        ctx["last_event"] = None
        logger.info(f"[session] 🆕 New session created for user={user_id}")
    else:
        # проверяем таймаут
        if last_seen:
            delta = now - last_seen
            if delta > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                ctx["session_id"] = _make_new_session_id(user_id)
                ctx["created_at"] = now
                ctx["actions_count"] = 0
                ctx["first_event"] = None
                ctx["last_event"] = None
                logger.info(
                    f"[session] 🔄 Session renewed for user={user_id} (idle {int(delta.total_seconds()/60)} min)"
                )
        else:
            ctx["last_seen"] = now

    # обновляем время последнего действия
    ctx["last_seen"] = now

    return ctx


def ensure_filters(user_id: int) -> dict:
    """
    Гарантирует, что в user_data[user_id] лежат актуальные фильтры.
    Если их нет — подтягивает из Supabase.
    """
    ctx = ensure_user_context(user_id)

    need_filters = any(
        key not in ctx
        for key in ("age_min", "age_max", "time_required", "energy", "location")
    )

    if need_filters:
        resp = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
        if resp.data:
            row = resp.data[0]
            ctx.setdefault("age_min", row.get("age_min"))
            ctx.setdefault("age_max", row.get("age_max"))
            ctx.setdefault("time_required", row.get("time_required"))
            ctx.setdefault("energy", row.get("energy"))
            ctx.setdefault("location", row.get("location"))

    return ctx
