import requests
import hashlib
import os
import sys

# --- НАСТРОЙКИ ---
# Если ты на Replit, адрес будет localhost:8000 (или твой URL)
TARGET_URL = "http://0.0.0.0:8000/robokassa/result" 
# Или внешний URL, если ты хочешь проверить прод: 
# TARGET_URL = "https://твое-приложение.replit.app/robokassa/result"

USER_ID = "276358220"  # Твой ID
AMOUNT = "490.00"
INV_ID = "777"         # Фейковый номер счета

# ВАЖНО: Пароль #2 от Робокассы (тот же, что в .env)
# Если скрипт падает, впиши сюда пароль руками временно
PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2", "TEST_PASS_2") 

def send_fake_payment():
    print(f"🚀 Имитируем оплату для user_id={USER_ID} на сумму {AMOUNT}...")

    # 1. Считаем подпись (MD5: OutSum:InvId:Password2)
    # Робокасса может слать Shp_user, но в подписи его нет (стандартная формула)
    sig_source = f"{AMOUNT}:{INV_ID}:{PASSWORD2}"
    signature = hashlib.md5(sig_source.encode()).hexdigest().upper()

    print(f"🔑 Подпись (SignatureValue): {signature}")

    # 2. Формируем данные (Form Data)
    payload = {
        "OutSum": AMOUNT,
        "InvId": INV_ID,
        "SignatureValue": signature,
        "Shp_user": USER_ID,        # Твой ID (важно!)
        "EMail": "test@fake.com",
        "IncCurrLabel": "BankCard"
    }

    # 3. Отправляем POST запрос
    try:
        response = requests.post(TARGET_URL, data=payload)

        print("\n📡 Ответ сервера:")
        print(f"Status Code: {response.status_code}")
        print(f"Body: {response.text}")

        if response.text.startswith("OK"):
            print("\n✅ УСПЕХ! Сервер принял оплату.")
            print("👉 Теперь проверь логи сервера и таблицы:")
            print("   1. user_subscriptions (должна появиться подписка)")
            print("   2. push_queue (должны исчезнуть старые пуши и появиться premium_welcome)")
        else:
            print("\n❌ ОШИБКА! Сервер не принял оплату. Проверь пароль или логи.")

    except Exception as e:
        print(f"\n💀 Ошибка соединения: {e}")
        print("Убедись, что сервер (uvicorn) запущен!")

if __name__ == "__main__":
    # Пытаемся подгрузить конфиг, если скрипт запущен из корня
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
        import config
        # Если в конфиге есть загрузка env, PASSWORD2 подтянется
        if os.getenv("ROBOKASSA_PASSWORD2"):
            PASSWORD2 = os.getenv("ROBOKASSA_PASSWORD2")
    except ImportError:
        pass

    send_fake_payment()