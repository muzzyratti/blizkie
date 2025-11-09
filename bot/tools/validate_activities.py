import os
from collections import defaultdict
from config import ENV
from db.supabase_client import supabase, TIME_MAP, ENERGY_MAP, location_MAP

print(f"✅ Запуск в окружении: {ENV}")

required_fields = ["title", "age_min", "age_max", "time_required", "energy", "location"]
valid_times = set(TIME_MAP.values())
valid_energies = set(ENERGY_MAP.values())
valid_locations = set(location_MAP.values())

print("🔍 Проверяем таблицу activities...\n")
activities = supabase.table("activities").select("*").execute().data or []

errors = []
titles_seen = set()
duplicates = []

for a in activities:
    aid = a.get("id")
    title = a.get("title", "").strip()

    # Проверка обязательных полей
    for field in required_fields:
        if not a.get(field):
            errors.append((aid, title, f"⚠️ Пустое поле {field}"))

    # Проверка возраста
    try:
        amin = int(a.get("age_min", 0))
        amax = int(a.get("age_max", 0))
        if amin > amax:
            errors.append((aid, title, "⚠️ age_min > age_max"))
    except ValueError:
        errors.append((aid, title, "⚠️ Некорректные значения возраста"))

    # Проверка дубликатов по названию
    if title in titles_seen:
        duplicates.append(title)
    else:
        titles_seen.add(title)

    # Проверка корректности категориальных полей
    def check_values(field, allowed):
        vals = [v.strip() for v in str(a.get(field, "")).split(",")]
        for v in vals:
            if v and v not in allowed:
                errors.append((aid, title, f"⚠️ Недопустимое значение {field}: {v}"))

    check_values("time_required", valid_times)
    check_values("energy", valid_energies)
    check_values("location", valid_locations)

# --- Вывод отчёта
print(f"Всего активностей: {len(activities)}")
print(f"Ошибок найдено: {len(errors)}")
print(f"Дубликатов названий: {len(duplicates)}\n")

if duplicates:
    print("=== ♻️ Дубликаты названий ===")
    for d in duplicates:
        print(f" - {d}")
    print()

if errors:
    print("=== ❌ Ошибки ===")
    for e in errors[:50]:
        print(f"[id={e[0]}] {e[1]} — {e[2]}")
    if len(errors) > 50:
        print(f"...и ещё {len(errors)-50} ошибок")
else:
    print("✅ Всё отлично, ошибок не найдено!")

print("\nГотово.\n")
