import os
import random
import logging
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

ENERGY_MAP = {
    "low": "Хочу просто спокойно пообщаться",
    "mid": "Немного бодрый — готов на лёгкую активность",
    "high": "Полон сил — хочу подвигаться!"
}

TIME_MAP = {
    "15": "15 мин",
    "30": "30 мин",
    "60": "1 час",
    "more": "Более часа"
}

location_MAP = {"outside": "На улице", "home": "Дома"}


def normalize(value: str) -> str:
    return value.lower().strip() if isinstance(value, str) else value


def get_activity(age: int, time_required: str, energy: str, location: str):
    logging.info(
        f"Фильтры: возраст={age}, время={time_required}, энергия={energy}, локация={location}"
    )

    response = supabase.table("activities").select("*").execute()
    activities = response.data
    logging.info(f"Всего активностей в БД: {len(activities)}")
    location_db = location_MAP.get(location, location)

    filtered = [
        a for a in activities
        if a.get("age_min") is not None and a.get("age_max") is not None
        and int(a["age_min"]) <= age <= int(a["age_max"])
        and normalize(a.get("time_required")) == normalize(time_required)
        and normalize(a.get("energy")) == normalize(energy)
        and normalize(a.get("location")) == normalize(location_db)
    ]

    logging.info(f"Подходящих активностей: {len(filtered)}")

    if not filtered:
        return None

    return random.choice(filtered)


def add_favorite(user_id: int, activity_id: int):
    # Проверяем нет ли уже в избранном
    exists = supabase.table("favorites").select("*").eq("user_id", user_id).eq(
        "activity_id", activity_id).execute()
    if exists.data:
        return False  # уже в избранном
    supabase.table("favorites").insert({
        "user_id": user_id,
        "activity_id": activity_id
    }).execute()
    return True


def remove_favorite(user_id: int, activity_id: int):
    supabase.table("favorites").delete().eq("user_id", user_id).eq(
        "activity_id", activity_id).execute()
    return True


def get_favorites(user_id: int):
    # Получаем список activity_id
    favs = supabase.table("favorites").select("activity_id").eq(
        "user_id", user_id).order("created_at", desc=True).execute()
    activity_ids = [f["activity_id"] for f in favs.data]
    if not activity_ids:
        return []
    # Получаем сами активности
    activities = supabase.table("activities").select("*").in_(
        "id", activity_ids).execute()
    # Сортируем в том порядке, как в избранном
    activities_map = {a["id"]: a for a in activities.data}
    return [activities_map[i] for i in activity_ids if i in activities_map]
