import sys
import os

# --- 1. НАСТРОЙКА ПУТЕЙ ---
# Скрипт лежит в bot/tools/ (или bot/scripts/), нам нужно видеть папку bot/
current_dir = os.path.dirname(os.path.abspath(__file__))
bot_dir = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.insert(0, bot_dir)

# --- 2. ГЛАВНЫЙ ФИНТ: ИМПОРТИРУЕМ КОНФИГ ---
# При импорте config.py сам выполнит load_dotenv() и загрузит нужные ключи
try:
    import config
    print(f"✅ Config загружен. Текущий ENV: {os.getenv('ENV')}")
except Exception as e:
    print(f"❌ Ошибка импорта config.py: {e}")
    sys.exit(1)

# --- 3. ТЕПЕРЬ ИМПОРТИРУЕМ БАЗУ ---
# Ключи уже в памяти, клиент создастся без ошибок
from db.supabase_client import supabase
from datetime import datetime, timezone

def create_test_push():
    user_id = 276358220  # Твой ID
    now_iso = datetime.now(timezone.utc).isoformat()

    print(f"🚀 Создаю тестовый пуш для user_id={user_id}...")

    data = {
        "user_id": user_id,
        "type": "retention_nudge", 
        "status": "pending",
        "scheduled_at": now_iso,
        "payload": {
            "step": 1,
            "is_test": True
        }
    }

    try:
        res = supabase.table("push_queue").insert(data).execute()

        # Получаем данные (в supabase-py v2 это res.data)
        rows = res.data if hasattr(res, 'data') else res

        if rows:
            print(f"✅ УСПЕХ! Пуш создан. ID: {rows[0]['id']}")
        else:
            print("⚠️ API вернул пустой ответ (но возможно запись прошла).")

    except Exception as e:
        print(f"❌ Ошибка записи в Supabase: {e}")

if __name__ == "__main__":
    create_test_push()