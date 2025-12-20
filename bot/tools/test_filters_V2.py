import sys, os
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, BASE_DIR)

import csv
from collections import Counter
from datetime import datetime

from config import ENV
from db.supabase_client import supabase, TIME_MAP, ENERGY_MAP, location_MAP
from db.seen import _matches_multivalue

print(f"✅ Загружено окружение: {ENV}")

# --- sanity check для _matches_multivalue ---
assert _matches_multivalue("Дома", "Дома, На улице"), "❌ Ошибка: _matches_multivalue работает неверно"
assert _matches_multivalue("На улице", "Дома, На улице"), "❌ Ошибка: _matches_multivalue работает неверно"
print("✅ Проверка _matches_multivalue() пройдена успешно\n")

# =========================
#   ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================

def bucket(count: int) -> str:
    """
    Категоризация количества идей под комбинацию фильтров.
    Нужно, чтобы быстро видеть, что болит.
    """
    if count == 0:
        return "critical_zero"   # 🔴 вообще нет идей
    elif count <= 3:
        return "low_1_3"         # 🟠 1–3 идеи — пользователь быстро всё прокликает
    elif count <= 7:
        return "ok_4_7"          # 🟡 нормально, но не роскошь
    else:
        return "good_8_plus"     # 🟢 хорошо покрыто


def color_for_bucket(bucket: str) -> str:
    """
    Цвет фона строки в HTML-отчёте.
    """
    if bucket == "critical_zero":
        return "#ffe3e3"  # красный
    if bucket == "low_1_3":
        return "#ffecc7"  # оранжевый
    if bucket == "ok_4_7":
        return "#fffbd1"  # жёлтый
    return "#e3ffe3"      # зелёный для good_8_plus


# =========================
#   ЗАГРУЗКА ДАННЫХ
# =========================

print("📥 Тянем активности из Supabase...")
activities = supabase.table("activities").select("*").execute().data or []
print(f"Всего активностей в базе: {len(activities)}\n")

print("📥 Тянем реальные фильтры пользователей из user_filters...")
uf_rows = supabase.table("user_filters") \
    .select("user_id, age_min, age_max, time_required, energy, location") \
    .execute().data or []

print(f"Всего записей в user_filters: {len(uf_rows)}\n")

if not uf_rows:
    print("❌ В user_filters нет данных — нечего анализировать.")
    exit(0)

# =========================
#   СБОР РЕАЛЬНЫХ КОМБО
# =========================

combos = []  # список комбинаций (age_min, age_max, time, energy, place)
for uf in uf_rows:
    age_min = uf.get("age_min")
    age_max = uf.get("age_max")
    time_code = uf.get("time_required")
    energy_code = uf.get("energy")
    location_code = uf.get("location")

    # маппим к человекочитаемым значениям, как в activities
    time_h = TIME_MAP.get(time_code, time_code)
    energy_h = ENERGY_MAP.get(energy_code, energy_code)
    place_h = location_MAP.get(location_code, location_code)

    combos.append((age_min, age_max, time_h, energy_h, place_h))

combo_counts = Counter(combos)  # (age_min, age_max, time_h, energy_h, place_h) -> N пользователей

print(f"🔍 Уникальных комбинаций фильтров: {len(combo_counts)}\n")

# =========================
#   ПОДБОР АКТИВНОСТЕЙ ПОД КАЖДУЮ КОМБО
# =========================

results = []

for (age_min, age_max, time_h, energy_h, place_h), users_count in combo_counts.items():
    found_activities = []

    for a in activities:
        try:
            a_age_min = int(a.get("age_min") or 0)
            a_age_max = int(a.get("age_max") or 0)
        except ValueError:
            continue

        # Пересечение возрастных диапазонов
        if a_age_max < age_min or a_age_min > age_max:
            continue

        # Сравниваем человекочитаемые значения через _matches_multivalue
        if not _matches_multivalue(time_h, a.get("time_required", "")):
            continue
        if not _matches_multivalue(energy_h, a.get("energy", "")):
            continue
        if not _matches_multivalue(place_h, a.get("location", "")):
            continue

        found_activities.append(a)

    count = len(found_activities)
    b = bucket(count)

    titles = ", ".join([a["title"] for a in found_activities])
    ids = ", ".join([str(a["id"]) for a in found_activities])

    results.append({
        "age_min": age_min,
        "age_max": age_max,
        "time": time_h,
        "energy": energy_h,
        "place": place_h,
        "users_count": users_count,
        "count": count,
        "bucket": b,
        "titles": titles,
        "ids": ids,
    })

# =========================
#   СТАТИСТИКА И ТОП ДЫР
# =========================

total_combos = len(results)
zeros = sum(1 for r in results if r["count"] == 0)
low_1_3 = sum(1 for r in results if 1 <= r["count"] <= 3)
ok_4_7 = sum(1 for r in results if 4 <= r["count"] <= 7)
good_8_plus = sum(1 for r in results if r["count"] >= 8)

print("=== 📊 ИТОГОВЫЙ ОТЧЁТ ПО РЕАЛЬНЫМ ФИЛЬТРАМ ===")
print(f"Всего уникальных комбинаций фильтров (по user_filters): {total_combos}")
print(f"Комбинаций с 0 идей (critical_zero): {zeros}")
print(f"Комбинаций с 1–3 идеями (low_1_3):   {low_1_3}")
print(f"Комбинаций с 4–7 идеями (ok_4_7):     {ok_4_7}")
print(f"Комбинаций с 8+ идеями (good_8_plus): {good_8_plus}\n")

# Топ "дыр" — где много пользователей и мало/нет идей
TOP_N = 15
problem_combos = [
    r for r in results
    if r["count"] <= 3  # критичные зоны: 0–3 идеи
]

problem_combos_sorted = sorted(
    problem_combos,
    key=lambda r: (-r["users_count"], r["count"])  # сначала по кол-ву пользователей, потом по кол-ву идей
)

print(f"=== 🔥 ТОП-{TOP_N} ПРОБЛЕМНЫХ КОМБИНАЦИЙ (много пользователей, мало идей) ===")
for r in problem_combos_sorted[:TOP_N]:
    print(
        f"{r['age_min']}-{r['age_max']} лет | {r['time']} | {r['energy'][:25]}... | {r['place']} → "
        f"пользователей: {r['users_count']}, идей: {r['count']} ({r['bucket']})"
    )

# =========================
#   CSV-ОТЧЁТ
# =========================

csv_path = "filter_coverage_real_combos.csv"
with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
    fieldnames = ["age_min", "age_max", "time", "energy", "place",
                  "users_count", "count", "bucket", "titles", "ids"]
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)

print(f"\n📁 CSV-отчёт сохранён: {csv_path}")

# =========================
#   HTML-ОТЧЁТ
# =========================

html_path = "filter_coverage_real_combos.html"
timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

html_head = f"""
<html>
<head>
<meta charset="utf-8">
<title>Отчёт по фильтрам (реальные комбинации) — Близкие Игры</title>
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
<h1>📊 Отчёт по фильтрам (реальные комбинации) — Близкие Игры</h1>
<p class="small">Дата генерации: {timestamp}</p>
<p><b>Всего уникальных комбинаций:</b> {total_combos}<br>
<b>0 идей:</b> {zeros} | <b>1–3 идей:</b> {low_1_3} | <b>4–7 идей:</b> {ok_4_7} | <b>8+ идей:</b> {good_8_plus}</p>
<p><b>Топ проблемных комбинаций (много пользователей, мало идей):</b></p>
<ul>
"""

for r in problem_combos_sorted[:TOP_N]:
    html_head += f"<li>{r['age_min']}-{r['age_max']} лет | {r['time']} | {r['energy']} | {r['place']} → пользователей: {r['users_count']}, идей: {r['count']} ({r['bucket']})</li>"

html_head += """
</ul>
<table id="resultsTable">
<tr>
  <th onclick="sortTable(0)">Возраст</th>
  <th onclick="sortTable(1)">Время</th>
  <th onclick="sortTable(2)">Энергия</th>
  <th onclick="sortTable(3)">Место</th>
  <th onclick="sortTable(4)">Пользователей</th>
  <th onclick="sortTable(5)">Идей</th>
  <th onclick="sortTable(6)">Категория</th>
  <th>Названия</th>
  <th>ID</th>
</tr>
"""

html_rows = ""
for r in results:
    bg = color_for_bucket(r["bucket"])
    html_rows += f"""
    <tr style="background-color: {bg};">
        <td>{r['age_min']}-{r['age_max']}</td>
        <td>{r['time']}</td>
        <td>{r['energy']}</td>
        <td>{r['place']}</td>
        <td>{r['users_count']}</td>
        <td>{r['count']}</td>
        <td>{r['bucket']}</td>
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

print(f"🌈 HTML-отчёт сохранён: {html_path}")
print("✅ Готово! Открой его в браузере и сразу увидишь, какие комбинации фильтров с реальным спросом покрыты плохо.")
