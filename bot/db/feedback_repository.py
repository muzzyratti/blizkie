from db.supabase_client import supabase
from datetime import datetime


def save_feedback(
    user_id: int,
    activity_id: int,
    rating: str,
    source: str,
    paywall_user: bool,
    filters: dict = None,
    optional_comment: str = None,
    session_id: str = None,
    upsert: bool = False,
):
    """
    Сохраняет фидбек по активности в таблицу feedback_activity.

    user_id, activity_id      — кто и про какую активность
    rating                    — 'super' | 'ok' | 'bad' | 'text'
    source                    — 'auto_prompt' | 'manual_button'
    paywall_user              — True/False (платящий сейчас)
    filters                   — dict с age_min/age_max/time_required/energy/location
    optional_comment          — текст юзера (если есть)
    session_id                — session_id из user_data (если есть)
    upsert                    — если True, перезаписываем запись того же user_id+activity_id
    """

    try:
        feedback_data = {
            "user_id": user_id,
            "activity_id": activity_id,
            "rating": rating,
            "source": source,
            "paywall_user": paywall_user,
            "optional_comment": optional_comment,
            "session_id": session_id,
            "created_at": datetime.utcnow().isoformat()
        }

        # докидываем фильтры, если они есть
        if filters:
            feedback_data.update({
                "age_min":        filters.get("age_min"),
                "age_max":        filters.get("age_max"),
                "time_required":  filters.get("time_required"),
                "energy":         filters.get("energy"),
                "location":       filters.get("location"),
            })

        # вставка или апсерт
        if upsert:
            supabase.table("feedback_activity") \
                .upsert(feedback_data, on_conflict="user_id,activity_id") \
                .execute()
        else:
            supabase.table("feedback_activity") \
                .insert(feedback_data) \
                .execute()

        print(f"[feedback_repository] ✅ saved user={user_id}, activity={activity_id}, upsert={upsert}")
        return True

    except Exception as e:
        print(f"[feedback_repository] ❌ Ошибка при сохранении фидбека: {e}")
        return False
