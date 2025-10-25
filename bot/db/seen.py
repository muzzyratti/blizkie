from datetime import datetime
from db.supabase_client import supabase, TIME_MAP, ENERGY_MAP, location_MAP
import logging
from random import choice


def _norm(s):
    return s.lower().strip() if isinstance(s, str) else ""


def _matches_multivalue(user_value: str, activity_value: str) -> bool:
    """
    user_value: то, что выбрал пользователь (например "home" или "15")
    activity_value: то, что лежит в базе (например "Дома, На улице" или "15 мин, 30 мин")

    Логика:
    1. маппим user_value через соответствующий MAP в человекочитаемый вид,
       чтобы сравнивать с тем, что лежит в базе
    2. режем activity_value по запятым и обрезаем пробелы
    3. сравниваем по нормализованной строке (lower/strip)
    """
    if activity_value is None:
        return False

    return _norm(user_value) in _norm(activity_value)


def get_next_activity_with_filters(user_id: int,
                                   age_min: int,
                                   age_max: int,
                                   time_required: str,
                                   energy: str,
                                   location: str):
    logging.info(
        f"[🔍 filters] user={user_id}, age_min={age_min}, age_max={age_max}, "
        f"time_required={time_required}, energy={energy}, location={location}"
    )

    # 1. маппинг значений из кодов пользователя -> человекочитаемые строки из базы
    mapped_time = TIME_MAP.get(time_required, time_required)
    mapped_energy = ENERGY_MAP.get(energy, energy)
    mapped_location = location_MAP.get(location, location)

    # 2. тащим все активности целиком
    activities_resp = supabase.table("activities").select("*").execute()
    activities = activities_resp.data or []
    logging.info(f"[📦 all_activities] всего {len(activities)} в базе")

    # 3. фильтруем активности питоном
    suitable_ids = []
    for a in activities:
        a_age_min = a.get("age_min")
        a_age_max = a.get("age_max")
        a_time = a.get("time_required", "")
        a_energy = a.get("energy", "")
        a_location = a.get("location", "")

        # возрастная проверка:
        # считаем, что игра подходит, если диапазоны пересекаются
        # (активность [a_min..a_max] пересекается с выбранной группой [age_min..age_max])
        if a_age_min is None or a_age_max is None:
            continue
        try:
            a_age_min = int(a_age_min)
            a_age_max = int(a_age_max)
        except ValueError:
            continue

        age_overlap = not (a_age_max < age_min or a_age_min > age_max)
        if not age_overlap:
            continue

        # проверка времени: выбранное значение должно "входить" в строку активности
        if not _matches_multivalue(mapped_time, a_time):
            continue

        # проверка энергии
        if not _matches_multivalue(mapped_energy, a_energy):
            continue

        # проверка локации
        if not _matches_multivalue(mapped_location, a_location):
            continue

        suitable_ids.append(a.get("id"))

    logging.info(f"[✅ suitable_ids] найдено {len(suitable_ids)} штук: {suitable_ids}")

    if not suitable_ids:
        logging.warning("[❌ empty] Нет подходящих активностей в базе по выбранным фильтрам")
        return None, False

    # 4. достаём уже показанные сессии для ЭТИХ ЖЕ фильтров
    seen_resp = supabase.table("seen_activities") \
        .select("activity_id") \
        .eq("user_id", user_id) \
        .eq("age_min", age_min) \
        .eq("age_max", age_max) \
        .eq("time_required", time_required) \
        .eq("energy", energy) \
        .eq("location", location) \
        .execute()

    seen_ids = [row["activity_id"] for row in (seen_resp.data or [])]
    logging.info(f"[👁️ seen_ids] уже показано {len(seen_ids)}: {seen_ids}")

    # 5. находим те, что еще не показывали
    unseen_ids = [aid for aid in suitable_ids if aid not in seen_ids]
    logging.info(f"[🆕 unseen_ids] осталось {len(unseen_ids)} непросмотренных")

    if unseen_ids:
        selected = choice(unseen_ids)
        logging.info(f"[🎯 pick] показываем id={selected}")
        return selected, False  # False = не ресетили

    # если всё уже показали, чистим историю просмотров по этим фильтрам и начинаем заново
    logging.info("[♻️ reset] все активности просмотрены — очищаем seen_activities для этих фильтров")

    supabase.table("seen_activities") \
        .delete() \
        .eq("user_id", user_id) \
        .eq("age_min", age_min) \
        .eq("age_max", age_max) \
        .eq("time_required", time_required) \
        .eq("energy", energy) \
        .eq("location", location) \
        .execute()

    selected = choice(suitable_ids)
    logging.info(f"[🔄 after reset] снова показываем id={selected}")
    return selected, True  # True = был ресет
