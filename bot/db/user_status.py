from db.supabase_client import supabase

def is_premium_user(user_id: int) -> bool:
    # 1) ручной оверрайд
    try:
        r = (supabase.table("premium_overrides")
             .select("is_premium")
             .eq("user_id", user_id).limit(1).execute())
        if (r.data and r.data[0].get("is_premium")):
            return True
    except Exception:
        pass

    # 2) активная подписка
    try:
        r2 = (supabase.table("user_subscriptions")
              .select("is_active, expires_at")
              .eq("user_id", user_id).limit(1).execute())
        row = (r2.data or [None])[0]
        if row and row.get("is_active"):
            # если на всякий случай проверять истечение
            return True
    except Exception:
        pass

    return False


def is_free_user(user_id: int) -> bool:
    return not is_premium_user(user_id)
