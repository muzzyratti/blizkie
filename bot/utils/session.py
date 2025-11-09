# utils/session.py
from handlers.user_state import user_data
from utils.session_tracker import touch_user_activity as _touch, _utcnow
from db.supabase_client import supabase
from utils.logger import setup_logger

logger = setup_logger()

def ensure_user_context(user_id: int) -> dict:
    """
    Единая точка входа: создаёт/продлевает сессию, обновляет last_seen.
    Больше НИЧЕГО не решаем здесь — вся логика в session_tracker.
    """
    _touch(user_id, source="tg")
    return user_data.setdefault(user_id, {})

def ensure_filters(user_id: int) -> dict:
    """
    Тянем фильтры из БД, если их ещё нет в user_data.
    """
    ctx = ensure_user_context(user_id)
    need = any(k not in ctx for k in ("age_min","age_max","time_required","energy","location"))
    if need:
        resp = supabase.table("user_filters").select("*").eq("user_id", user_id).execute()
        if resp.data:
            row = resp.data[0]
            ctx.setdefault("age_min", row.get("age_min"))
            ctx.setdefault("age_max", row.get("age_max"))
            ctx.setdefault("time_required", row.get("time_required"))
            ctx.setdefault("energy", row.get("energy"))
            ctx.setdefault("location", row.get("location"))
    return ctx
