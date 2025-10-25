import os
from config import ENV
from db.seen import get_next_activity_with_filters
from db.supabase_client import supabase

print(f"✅ Запуск в окружении: {ENV}")

# Ввод фильтров
user_id = 999999  # тестовый ID, неважен
age_min = int(input("Возраст (мин): ") or 5)
age_max = int(input("Возраст (макс): ") or 6)
time_required = input("Время ('15 мин', '30 мин', '1 час', 'Более часа'): ") or "15 мин"
energy = input("Энергия ('Хочу просто спокойно пообщаться', 'Немного бодрый — готов на лёгкую активность', 'Полон сил — хочу подвигаться!'): ") or "Немного бодрый — готов на лёгкую активность"
location = input("Локация ('Дома', 'На улице'): ") or "Дома"

print("\n🔍 Ищем подходящие активности...\n")

# Тащим все активности из БД
activities_resp = supabase.table("activities").select("*").execute()
activities = activities_resp.data or []

# Используем внутреннюю логику
from db.seen import _matches_multivalue

suitable = []
for a in activities:
    try:
        amin, amax = int(a.get("age_min", 0)), int(a.get("age_max", 0))
        if amax < age_min or amin > age_max:
            continue
    except:
        continue

    if not _matches_multivalue(time_required, a.get("time_required", "")):
        continue
    if not _matches_multivalue(energy, a.get("energy", "")):
        continue
    if not _matches_multivalue(location, a.get("location", "")):
        continue

    suitable.append(a)

if not suitable:
    print("❌ Ничего не найдено.")
else:
    print(f"✅ Найдено {len(suitable)} активностей:\n")
    for a in suitable:
        print(f"🎲 {a['id']:>4} | {a['title']} | {a['time_required']} | {a['energy']} | {a['location']}")
    print("\nВсего:", len(suitable))
