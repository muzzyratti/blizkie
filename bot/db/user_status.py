from db.supabase_client import supabase

def is_premium_user(user_id: int) -> bool:
    """
    Источник правды — таблица premium_overrides (ручные апгрейды).
    Позже сюда добавим check из таблицы subscriptions.
    """
    try:
        r = (
            supabase.table("premium_overrides")
            .select("is_premium")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        return bool(rows and rows[0].get("is_premium"))
    except Exception as e:
        print(f"[user_status] premium_overrides lookup error for user={user_id}: {e}")
        return False


def is_free_user(user_id: int) -> bool:
    return not is_premium_user(user_id)
