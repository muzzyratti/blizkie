import time
from db.supabase_client import supabase

# Простое кэширование фич-флагов в памяти
_CACHE = {"data": {}, "ts": 0}
CACHE_TTL_SECONDS = 30  # обновляем кэш не чаще, чем раз в 30 секунд


def _load_flags_from_db() -> dict:
    """Загружает все фичи из Supabase одним запросом."""
    try:
        resp = supabase.table("feature_flags").select("*").execute()
        data = {}
        for row in resp.data or []:
            key = row.get("key")
            val = row.get("value_json") or {}
            if key:
                data[key] = val
        return data
    except Exception:
        return {}


def _ensure_cache():
    now = time.time()
    if (now - _CACHE["ts"] > CACHE_TTL_SECONDS) or not _CACHE["data"]:
        _CACHE["data"] = _load_flags_from_db()
        _CACHE["ts"] = now


def get_flag(key: str, default: dict | None = None) -> dict:
    """Возвращает значение фичи по ключу (или default)."""
    _ensure_cache()
    val = _CACHE["data"].get(key)
    return val if isinstance(val, dict) else (default or {})


def is_enabled(key: str, default: bool = True) -> bool:
    """Быстрая проверка включённости фичи (через поле enabled)."""
    flag = get_flag(key)
    return bool(flag.get("enabled", default))


def get_microfeedback_auto_config() -> dict:
    """
    Конфиг авто-микрофидбека после показа L1-карточек.

    Ожидаемый JSON в feature_flags.value_json:
    {
      "enabled": true,
      "free_intervals": [3,5,7],
      "premium_intervals": [7,12],
      "cooldown_minutes": 20
    }
    """
    cfg = get_flag("microfeedback_auto_config", {})
    defaults = {
        "enabled": True,
        "free_intervals": [3, 5, 7],
        "premium_intervals": [7, 12],
        "cooldown_minutes": 20,
    }

    # Сливаем с дефолтами
    merged = {**defaults, **cfg}

    # Нормализуем типы
    def normalize_list(val):
        if not isinstance(val, list):
            return []
        out = []
        for x in val:
            try:
                xi = int(x)
                if xi > 0:
                    out.append(xi)
            except Exception:
                continue
        return out

    merged["free_intervals"] = normalize_list(merged.get("free_intervals"))
    merged["premium_intervals"] = normalize_list(merged.get("premium_intervals"))

    try:
        merged["cooldown_minutes"] = int(merged.get("cooldown_minutes", defaults["cooldown_minutes"]))
    except Exception:
        merged["cooldown_minutes"] = defaults["cooldown_minutes"]

    merged["enabled"] = bool(merged.get("enabled", True))
    return merged
