from db.supabase_client import supabase
from db.feature_flags import get_flag

def is_premium(user_id: int) -> bool:
    try:
        r = (supabase.table("premium_overrides")
             .select("is_premium")
             .eq("user_id", user_id)
             .limit(1)
             .execute())
        rows = r.data or []
        return bool(rows and rows[0].get("is_premium"))
    except Exception as e:
        print(f"[paywall_guard] premium_overrides lookup error for user={user_id}: {e}")
        return False

def _rules():
    cfg = get_flag("paywall_rules") or {}
    if not cfg.get("enabled", True):
        return None
    # дефолты
    l1 = int(cfg.get("l1_limit", 5))
    l0 = int(cfg.get("l0_limit", 15))
    return {"l1": l1, "l0": l0}

def l1_views_count(user_id: int) -> int:
    try:
        res = (supabase.table("seen_activities")
               .select("activity_id", count="exact")
               .eq("user_id", user_id)
               .eq("level", "l1")
               .execute())
        return int(res.count or 0)
    except Exception as e:
        print(f"[paywall_guard] L1 views count error for user={user_id}: {e}")
        return 0

def l0_views_count(user_id: int) -> int:
    try:
        res = (supabase.table("seen_activities")
               .select("activity_id", count="exact")
               .eq("user_id", user_id)
               .eq("level", "l0")
               .execute())
        return int(res.count or 0)
    except Exception as e:
        print(f"[paywall_guard] L0 views count error for user={user_id}: {e}")
        return 0

def should_block_l1(user_id: int) -> bool:
    rules = _rules()
    if not rules or is_premium(user_id):
        return False
    return l1_views_count(user_id) >= rules["l1"]

def should_block_l0(user_id: int) -> bool:
    """
    Блокируем L0, если суммарно просмотрено >= l0_limit (по жизни).
    Это работает независимо от L1, но в твоей логике:
    - L1 блокируется после 5,
    - L0 блокируется после 15 всего.
    """
    rules = _rules()
    if not rules or is_premium(user_id):
        return False
    return l0_views_count(user_id) >= rules["l0"]

def is_user_limited(user_id: int) -> bool:
    """
    True, если юзер достиг лимита бесплатных L1 карточек.
    """
    try:
        return should_block_l1(user_id)   # <-- вот правильная проверка лимита
    except Exception as e:
        print(f"[paywall_guard] is_user_limited err user={user_id}: {e}")
        return False