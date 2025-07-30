from datetime import datetime
from db.supabase_client import supabase


def get_next_activity_with_filters(user_id: int, age: int, time: str,
                                   energy: str, place: str):
    # 1. Получаем все подходящие активности
    activities = supabase.table("activities") \
        .select("id") \
        .eq("age_min", age) \
        .execute().data

    all_ids = [a["id"] for a in activities]

    # 2. Получаем просмотренные
    seen = supabase.table("seen_activities") \
        .select("activity_id") \
        .eq("user_id", user_id) \
        .eq("age", age) \
        .eq("time", time) \
        .eq("energy", energy) \
        .eq("place", place) \
        .execute().data

    seen_ids = [s["activity_id"] for s in seen]

    # 3. Вычисляем непоказанные
    unseen_ids = list(set(all_ids) - set(seen_ids))

    if unseen_ids:
        from random import choice
        return choice(unseen_ids), False  # False = не все показаны
    else:
        # Сбрасываем seen
        supabase.table("seen_activities") \
            .delete() \
            .eq("user_id", user_id) \
            .eq("age", age) \
            .eq("time", time) \
            .eq("energy", energy) \
            .eq("place", place) \
            .execute()

        from random import choice
        return choice(all_ids), True  # True = был ресет
