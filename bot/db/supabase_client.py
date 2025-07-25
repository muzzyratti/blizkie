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

PLACE_MAP = {
    "home": "Дома",
    "outside": "На улице"
}


def normalize(value: str) -> str:
    return value.lower().strip() if isinstance(value, str) else value

def get_activity(age: int, time_required: str, energy: str, location: str):
    logging.info(f"Фильтры: возраст={age}, время={time_required}, энергия={energy}, локация={location}")

    response = supabase.table("activities").select("*").execute()
    activities = response.data
    logging.info(f"Всего активностей в БД: {len(activities)}")

    filtered = [
        a for a in activities
        if a.get("age_min") is not None and a.get("age_max") is not None
        and a["age_min"] <= age <= a["age_max"]
        and normalize(a.get("time_required")) == normalize(time_required)
        and normalize(a.get("energy")) == normalize(energy)
        and normalize(a.get("location")) == normalize(location)
    ]

    logging.info(f"Подходящих активностей: {len(filtered)}")

    if not filtered:
        return None

    return random.choice(filtered)
