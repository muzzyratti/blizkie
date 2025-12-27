from db.supabase_client import supabase
from db.feature_flags import get_flag
from datetime import datetime, timedelta, timezone

# --- PREMIUM CHECK ---
try:
    from db.user_status import is_premium_user as _is_premium_user
except Exception:
    _is_premium_user = None

def is_premium(user_id: int) -> bool:
    if _is_premium_user:
        try:
            return bool(_is_premium_user(user_id))
        except Exception as e:
            print(f"[paywall_guard] fallback error: {e}")

    try:
        r = supabase.table("premium_overrides").select("is_premium").eq("user_id", user_id).limit(1).execute()
        rows = r.data or []
        return bool(rows and rows[0].get("is_premium"))
    except Exception as e:
        print(f"[paywall_guard] overrides error: {e}")
        return False

# --- CONFIGS ---

def _get_paywall_config():
    """
    Возвращает конфиг лимитов.
    Если enabled=False, возвращает None (лимиты выключены ГЛОБАЛЬНО).
    """
    cfg = get_flag("paywall_rules") or {}
    if not cfg.get("enabled", True):
        return None
    return {
        "l1": int(cfg.get("l1_limit", 5)),
        "l0": int(cfg.get("l0_limit", 15))
    }

def _get_trial_config():
    """
    Возвращает кол-во дней триала.
    Пример JSON в feature_flags (ключ: trial_policy): { "enabled": true, "days": 14 }
    """
    cfg = get_flag("trial_policy") or {}
    if not cfg.get("enabled", False):
        return None
    return int(cfg.get("days", 0))

# --- TRIAL LOGIC (FIXED) ---

def is_in_trial(user_id: int) -> bool:
    """
    Проверяет, находится ли юзер в триальном периоде.
    Берет дату САМОЙ ПЕРВОЙ сессии из user_sessions как дату регистрации.
    """
    trial_days = _get_trial_config()
    if not trial_days:
        return False  # Триал выключен

    try:
        # Ищем самую старую сессию пользователя
        res = (supabase.table("user_sessions")
               .select("created_at")
               .eq("user_id", user_id)
               .order("created_at", desc=False) # Сортируем: старые сверху
               .limit(1)                        # Берем одну (первую)
               .execute())

        if not res.data:
            # Если сессий нет (странно, но бывает), считаем что он "новенький" -> триал активен
            return True

        created_at_str = res.data[0].get("created_at")
        if not created_at_str:
            return True

        # Парсим дату
        # Обработка разных форматов времени (с точкой и без)
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
        except ValueError:
             # Fallback для форматов без таймзоны, если вдруг такие попадут
            created_at = datetime.fromisoformat(created_at_str).replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)

        # Если прошло меньше дней, чем trial_days -> True
        return (now - created_at).days < trial_days

    except Exception as e:
        print(f"[paywall_guard] trial check error for {user_id}: {e}")
        # В случае ошибки лучше НЕ блокировать (Fail Open), чтобы не злить юзера багами
        return True 

# --- VIEWS COUNTERS ---

def l1_views_count(user_id: int) -> int:
    try:
        res = (supabase.table("seen_activities")
               .select("activity_id", count="exact")
               .eq("user_id", user_id)
               .eq("level", "l1")
               .execute())
        return int(res.count or 0)
    except Exception:
        return 0

def l0_views_count(user_id: int) -> int:
    try:
        res = (supabase.table("seen_activities")
               .select("activity_id", count="exact")
               .eq("user_id", user_id)
               .eq("level", "l0")
               .execute())
        return int(res.count or 0)
    except Exception:
        return 0

# --- MAIN LOGIC ---

def should_block_l1(user_id: int) -> bool:
    if is_premium(user_id): return False

    # Сначала проверяем триал (если юзеру < 14 дней, не блокируем)
    if is_in_trial(user_id): return False

    rules = _get_paywall_config()
    if rules is None: return False # Глобальное отключение

    return l1_views_count(user_id) >= rules["l1"]

def should_block_l0(user_id: int) -> bool:
    if is_premium(user_id): return False

    if is_in_trial(user_id): return False

    rules = _get_paywall_config()
    if rules is None: return False 

    return l0_views_count(user_id) >= rules["l0"]

def is_user_limited(user_id: int) -> bool:
    try:
        return should_block_l1(user_id) or should_block_l0(user_id)
    except Exception as e:
        print(f"[paywall_guard] is_user_limited err user={user_id}: {e}")
        return False

# --- ALIAS FOR BACKWARD COMPATIBILITY ---
_rules = _get_paywall_config