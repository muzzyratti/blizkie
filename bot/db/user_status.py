# bot/db/user_status.py
from db.supabase_client import supabase
from datetime import datetime, timezone

def is_premium_user(user_id: int) -> bool:
    # 1) ручной оверрайд
    try:
        r = (
            supabase.table("premium_overrides")
            .select("is_premium")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if r.data and r.data[0].get("is_premium"):
            return True
    except Exception:
        pass

    # 2) активная подписка
    try:
        r2 = (
            supabase.table("user_subscriptions")
            .select("is_active, expires_at")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        row = (r2.data or [None])[0]
        if row and row.get("is_active"):
            expires_at = row.get("expires_at")
            if expires_at:
                try:
                    exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if exp > datetime.now(timezone.utc):
                        return True
                except Exception:
                    # если формат странный — считаем активным (лучше доступ, чем блок)
                    return True
            else:
                # если нет expires_at, но is_active=True
                return True
    except Exception:
        pass

    return False


def is_free_user(user_id: int) -> bool:
    return not is_premium_user(user_id)
