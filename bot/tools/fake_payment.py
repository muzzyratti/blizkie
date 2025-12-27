import requests
import hashlib
import os
import sys
from dotenv import load_dotenv

# ---------------------------------------------------------
# 1. РУЧНАЯ ЗАГРУЗКА ENV (КАК В CONFIG.PY)
# ---------------------------------------------------------
# Считаем, что запускаем из корня проекта ~/blizkie
root_dir = os.path.abspath(".") 

# 1) Грузим базовый .env
base_env = os.path.join(root_dir, ".env")
if os.path.exists(base_env):
    load_dotenv(base_env)

# 2) Определяем среду (dev/prod)
env_mode = os.getenv("ENV", "dev")
target_env_file = os.path.join(root_dir, f".env.{env_mode}")

# 3) Грузим целевой .env (переопределяем значения)
if os.path.exists(target_env_file):
    load_dotenv(target_env_file, override=True)
    print(f"✅ Загружен конфиг: .env.{env_mode}")
else:
    print(f"⚠️ Файл .env.{env_mode} не найден, используем базовый .env")

# ---------------------------------------------------------
# 2. НАСТРОЙКА ПУТЕЙ ДЛЯ ИМПОРТА
# ---------------------------------------------------------
# Добавляем 'bot' и корень в sys.path
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
bot_path = os.path.join(root_dir, "bot")
if bot_path not in sys.path:
    sys.path.insert(0, bot_path)

# ---------------------------------------------------------
# 3. ИМПОРТ И РАБОТА
# ---------------------------------------------------------
try:
    from db.feature_flags import get_flag
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Ошибка инициализации БД: {e}")
    print("Проверь SUPABASE_URL и SUPABASE_KEY в .env!")
    sys.exit(1)

TARGET_URL = "http://127.0.0.1:8000/robokassa/result" 
USER_ID = "276358220"
AMOUNT = "490.00"
INV_ID = "777888" # Уникальный ID

def send_fake_payment():
    print("🔄 Тянем пароль из БД...")
    rk_keys = get_flag("robokassa_keys", {})
    password2 = rk_keys.get("password2")

    if not password2:
        print("❌ Ошибка: password2 не найден в feature_flags!")
        return

    print(f"✅ Пароль получен: {password2[:3]}...{password2[-3:]}")

    sig_source = f"{AMOUNT}:{INV_ID}:{password2}"
    signature = hashlib.md5(sig_source.encode()).hexdigest().upper()

    payload = {
        "OutSum": AMOUNT,
        "InvId": INV_ID,
        "SignatureValue": signature,
        "Shp_user": USER_ID,
        "EMail": "autonomous_test@fake.com",
        "IncCurrLabel": "BankCard"
    }

    try:
        response = requests.post(TARGET_URL, data=payload)
        print(f"\n📡 Ответ сервера: {response.status_code}")
        if response.status_code == 200 and "OK" in response.text:
            print("✅ УСПЕХ! Оплата прошла.")
        else:
            print(f"❌ ОШИБКА! Body: {response.text}")

    except Exception as e:
        print(f"\n💀 Ошибка соединения: {e}")

if __name__ == "__main__":
    send_fake_payment()