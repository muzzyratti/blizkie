import time
from db.supabase_client import supabase

_cache = {
    "data": {},
    "ts": 0  # timestamp последней загрузки
}

CACHE_TTL_SECONDS = 30  # чтобы не бомбить supabase на каждый показ карточки


def _load_flags_from_db():
    resp = supabase.table("feature_flags").select("*").execute()
    data = {}
    for row in resp.data or []:
        key = row.get("key")
        val = row.get("value_json")
        if key:
            data[key] = val
    return data


def _ensure_cache():
    now = time.time()
    if now - _cache["ts"] > CACHE_TTL_SECONDS or not _cache["data"]:
        _cache["data"] = _load_flags_from_db()
        _cache["ts"] = now


def get_flag(key: str, default=None):
    _ensure_cache()
    return _cache["data"].get(key, default)


def is_enabled(key: str, default=True):
    flag = get_flag(key, {})
    return flag.get("enabled", default) if isinstance(flag, dict) else default


def get_microfeedback_config():
    cfg = get_flag("microfeedback_config", {}) or {}
    return {
        "enabled": cfg.get("enabled", True),
        "free_interval": cfg.get("free_interval", 3),
        "paid_interval": cfg.get("paid_interval", 10),
        "allow_text": cfg.get("allow_text", True),
    }
