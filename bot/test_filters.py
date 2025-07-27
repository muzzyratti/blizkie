import os
import csv
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
from db.supabase_client import get_activity

# Загружаем переменные окружения из .env
load_dotenv()

# Тестовые параметры
ages = [3, 4, 5, 6, 7, 8]
times = ["15 мин", "30 мин", "1 час", "Более часа"]
energies = [
    "Хочу просто спокойно пообщаться",
    "Немного бодрый — готов на лёгкую активность",
    "Полон сил — хочу подвигаться!"
]
places = ["Дома", "На улице"]

# Результаты
results = []

print("Запускаем массовый тест фильтров...\n")

for age in ages:
    for time in times:
        for energy in energies:
            for place in places:
                activity = get_activity(age, time, energy, place)
                found = activity is not None
                results.append({
                    "age": age,
                    "time": time,
                    "energy": energy,
                    "place": place,
                    "found": found,
                    "title": activity["title"] if found else ""
                })
                print(
                    f"[{age} лет | {time} | {energy} | {place}] → "
                    f"{'Найдена: ' + activity['title'] if found else 'НЕТ идей'}"
                )

# Записываем в CSV
output_path = "test_results.csv"
with open(output_path, "w", newline="", encoding="utf-8") as csvfile:
    fieldnames = ["age", "time", "energy", "place", "found", "title"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in results:
        writer.writerow(row)

# Краткая статистика
total = len(results)
found_count = sum(1 for r in results if r["found"])
not_found_count = total - found_count

print("\n=== РЕЗУЛЬТАТЫ ТЕСТА ===")
print(f"Всего комбинаций: {total}")
print(f"С идеями: {found_count}")
print(f"Без идей: {not_found_count}")
print(f"CSV сохранён: {output_path}")
