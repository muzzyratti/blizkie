from db.supabase_client import supabase
from datetime import datetime


def save_user_session(user_id: int, filters: dict):
    session_data = {
        "user_id": user_id,
        "age": filters.get("age"),
        "time": filters.get("time"),
        "energy": filters.get("energy"),
        "place": filters.get("place"),
        "session_id": filters.get("session_id"),
        "subscribed_to_channel": filters.get("subscribed_to_channel")
    }

    # Удаляем ключи, у которых значение None — иначе упадёт insert
    clean_data = {k: v for k, v in session_data.items() if v is not None}

    existing = supabase.table("user_sessions").select("*").eq(
        "user_id", user_id).execute()
    if existing.data:
        supabase.table("user_sessions").update(clean_data).eq(
            "user_id", user_id).execute()
    else:
        supabase.table("user_sessions").insert(clean_data).execute()


def load_user_session(user_id: int) -> dict | None:
    """Загружает сессию пользователя, если есть"""
    try:
        response = supabase.table("user_sessions").select("*").eq(
            "user_id", user_id).execute()
        if response.data:
            return response.data[0]
    except Exception as e:
        print(f"[Supabase] Ошибка при загрузке сессии: {e}")
    return None
