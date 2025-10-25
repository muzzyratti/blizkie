import os
import csv
from collections import defaultdict
from datetime import datetime

# ✅ Подключаем конфиг (.env.dev или .env.prod)
from config import ENV
from db.supabase_client import supabase, TIME_MAP, ENERGY_MAP, location_MAP
from db.seen import _matches_multivalue

print(f"✅ Загружено окружение: {ENV}")

# --- sanity check для _matches_multivalue ---
assert _matches_multivalue("Дома", "Дома, На улице"), "❌ Ошибка: _matches_multivalue работает неверно"
assert _matches_multivalue("На улице", "Дома, На улице"), "❌ Ошибка: _matches_multivalue работает неверно"
print("✅ Проверка _matches_multivalue() пройдена успешно\n")

# --- тестовые диапазоны ---
age_groups = [(3, 4), (5, 6), (7, 8), (9, 10)]
times = list(TIME_MAP.values())
energies = list(ENERGY_MAP.values())
locations = list(location_MAP.values())

results = []
gaps_by_field = defaultdict(int)

print("🚀 Запускаем массовый тест фильтров (диапазоны + мультизначения)...\n")

activities = supabase.table("activities").select("*").execute().data or []
print(f"Всего активностей в базе: {len(activities)}\n")

# --- основной цикл ---
for (age_min, age_max) in age_groups:
    for time in times:
        for energy in energies:
            for place in locations:
                found_activities = []

                for a in activities:
                    try:
                        a_age_min = int(a.get("age_min") or 0)
                        a_age_max = int(a.get("age_max") or 0)
                    except ValueError:
                        continue

                    # Проверяем пересечение возрастных диапазонов
                    if a_age_max < age_min or a_age_min > age_max:
                        continue

                    # ✅ правильный порядок аргументов — пользователь → база
                    if not _matches_multivalue(time, a.get("time_required", "")):
                        continue
                    if not _matches_multivalue(energy, a.get("energy", "")):
                        continue
                    if not _matches_multivalue(place, a.get("location", "")):
                        continue

                    found_activities.append(a)

                found = len(found_activities) > 0
                if not found:
                    gaps_by_field[f"{age_min}-{age_max} лет"] += 1
                    gaps_by_field[time] += 1
                    gaps_by_field[energy] += 1
                    gaps_by_field[place] += 1

                titles = ", ".join([a["title"] for a in found_activities])
                ids = ", ".join([str(a["id"]) for a in found_activities])

                results.append({
                    "age_min": age_min,
                    "age_max": age_max,
                    "time": time,
                    "energy": energy,
                    "place": place,
                    "found": found,
                    "count": len(found_activities),
                    "titles": titles,
                    "ids": ids
                })

                symbol = "✅" if found else "❌"
                status = f"{len(found_activities)} идей" if found else "нет идей"
                print(f"{symbol} [{age_min}-{age_max} | {time} | {energy[:25]}... | {place}] → {status}")

# --- сохраняем CSV ---
csv_path = "test_results_full.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
    fieldnames = ["age_min", "age_max", "time", "energy", "place", "found", "count", "titles", "ids"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

# --- итоговая статистика ---
total = len(results)
found_count = sum(1 for r in results if r["found"])
not_found_count = total - found_count
coverage = round(found_count / total * 100, 1)

print("\n=== 📊 ИТОГОВЫЙ ОТЧЁТ ===")
print(f"Всего комбинаций: {total}")
print(f"С идеями: {found_count}")
print(f"Без идей: {not_found_count}")
print(f"Покрытие базы: {coverage}%")
print(f"CSV сохранён: {csv_path}")

# --- анализ пропусков ---
if not_found_count > 0:
    print("\n=== 🔍 АНАЛИЗ ПРОПУСКОВ ===")
    sorted_gaps = sorted(gaps_by_field.items(), key=lambda x: x[1], reverse=True)
    for field, count in sorted_gaps[:10]:
        print(f"⚠️ {field}: {count} комбинаций без идей")

# --- HTML-отчёт ---
html_path = "test_results_full.html"
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

html_head = f"""
<html>
<head>
<meta charset="utf-8">
<title>Отчёт по тесту фильтров — Близкие Игры</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 40px;
    background: #fafafa;
}}
h1 {{
    text-align: center;
}}
table {{
    border-collapse: collapse;
    width: 100%;
    margin-top: 20px;
}}
th, td {{
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}}
th {{
    background-color: #f2f2f2;
    cursor: pointer;
}}
tr:hover {{ background-color: #f5f5f5; }}
.found {{ background-color: #e3ffe3; }}
.notfound {{ background-color: #ffe3e3; }}
.small {{
    font-size: 13px;
    color: #666;
}}
</style>
<script>
function sortTable(n) {{
  var table, rows, switching, i, x, y, shouldSwitch, dir, switchcount = 0;
  table = document.getElementById("resultsTable");
  switching = true;
  dir = "asc";
  while (switching) {{
    switching = false;
    rows = table.rows;
    for (i = 1; i < (rows.length - 1); i++) {{
      shouldSwitch = false;
      x = rows[i].getElementsByTagName("TD")[n];
      y = rows[i + 1].getElementsByTagName("TD")[n];
      if (dir == "asc") {{
        if (x.innerHTML.toLowerCase() > y.innerHTML.toLowerCase()) {{
          shouldSwitch = true;
          break;
        }}
      }} else if (dir == "desc") {{
        if (x.innerHTML.toLowerCase() < y.innerHTML.toLowerCase()) {{
          shouldSwitch = true;
          break;
        }}
      }}
    }}
    if (shouldSwitch) {{
      rows[i].parentNode.insertBefore(rows[i + 1], rows[i]);
      switching = true;
      switchcount ++;
    }} else {{
      if (switchcount == 0 && dir == "asc") {{
        dir = "desc";
        switching = true;
      }}
    }}
  }}
}}
</script>
</head>
<body>
<h1>📊 Отчёт по тесту фильтров — Близкие Игры</h1>
<p class="small">Дата генерации: {timestamp}</p>
<p><b>Покрытие базы:</b> {coverage}%<br>
<b>Всего комбинаций:</b> {total} | <b>С идеями:</b> {found_count} | <b>Без идей:</b> {not_found_count}</p>
<table id="resultsTable">
<tr>
  <th onclick="sortTable(0)">Возраст</th>
  <th onclick="sortTable(1)">Время</th>
  <th onclick="sortTable(2)">Энергия</th>
  <th onclick="sortTable(3)">Место</th>
  <th onclick="sortTable(4)">Идей</th>
  <th>Названия</th>
  <th>ID</th>
</tr>
"""

html_rows = ""
for r in results:
    cls = "found" if r["found"] else "notfound"
    html_rows += f"""
    <tr class="{cls}">
        <td>{r['age_min']}-{r['age_max']}</td>
        <td>{r['time']}</td>
        <td>{r['energy']}</td>
        <td>{r['place']}</td>
        <td>{r['count']}</td>
        <td>{r['titles']}</td>
        <td>{r['ids']}</td>
    </tr>
    """

html_end = """
</table>
</body>
</html>
"""

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_head + html_rows + html_end)

print(f"\n🌈 HTML отчёт сохранён: {html_path}")
print("✅ Готово! Открой его в браузере, чтобы визуально проверить покрытие.")
