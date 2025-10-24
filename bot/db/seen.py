from datetime import datetime
from db.supabase_client import supabase, TIME_MAP, ENERGY_MAP, location_MAP
import logging
from random import choice


def get_next_activity_with_filters(user_id: int, age: int, time: str,
                                   energy: str, location: str):
    logging.info(
        f"[🔍 filters] user={user_id}, age={age}, time={time}, energy={energy}, location={location}"
    )

    # 1. Получаем все подходящие активности
    mapped_location = location_MAP.get(location, location)
    mapped_energy = ENERGY_MAP.get(energy, energy)
    mapped_time = TIME_MAP.get(time, time)

    activities = supabase.table("activities") \
    .select("id") \
    .lte("age_min", age) \
    .gte("age_max", age) \
    .eq("time_required", mapped_time) \
    .eq("energy", mapped_energy) \
    .eq("location", mapped_location) \
    .execute().data

    all_ids = [a["id"] for a in activities]
    logging.info(f"[📦 all_ids] найдено {len(all_ids)} активностей")

    if not all_ids:
        logging.warning(
            "[❌ empty] Нет подходящих активностей в базе по выбранным фильтрам"
        )
        return None, False

    # 2. Получаем просмотренные
    seen = supabase.table("seen_activities") \
        .select("activity_id") \
        .eq("user_id", user_id) \
        .eq("age", age) \
        .eq("time", time) \
        .eq("energy", energy) \
        .eq("location", location) \
        .execute().data

    seen_ids = [s["activity_id"] for s in seen]
    logging.info(f"[👁️ seen] просмотрено {len(seen_ids)}")

    # 3. Вычисляем непоказанные
    unseen_ids = list(set(all_ids) - set(seen_ids))
    logging.info(f"[🆕 unseen] осталось {len(unseen_ids)} непросмотренных")

    if unseen_ids:
        selected = choice(unseen_ids)
        logging.info(f"[✅ choice] выбран id={selected}")
        return selected, False  # False = не все показаны

    if not all_ids:
        logging.warning(
            "[❌ empty] Нет подходящих активностей в базе по выбранным фильтрам"
        )
        return None, False

    logging.info("[♻️ reset] все активности просмотрены — сбрасываем")
    supabase.table("seen_activities") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("age", age) \
        .eq("time", time) \
        .eq("energy", energy) \
        .eq("location", location) \
        .execute()

    selected = choice(all_ids)
    logging.info(f"[🔄 after reset] выбран id={selected}")
    return selected, True  # True = был ресет
