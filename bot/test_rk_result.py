# scripts/test_rk_result.py
import hashlib
import requests
import time
from datetime import datetime
import urllib3
import os

# --- отключаем предупреждения о self-signed сертификате ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Конфигурация ---
VPS_BASE = "https://194.54.156.170"      # внешний IP VPS
USER_ID  = 276358220                     # тестовый Telegram user_id
OUT_SUM  = "490.00"                      # сумма (как в настройках)
INV_ID   = str(int(time.time()))         # фиктивный номер счёта
IS_TEST  = "1"                           # эмуляция тестового режима
PASSWORD2 = "K8YSV68WNkYzVSeh52YF"       # robokassa_keys.password2

# --- Подпись для RESULT-запроса ---
# Формула Robokassa: md5(f"{OutSum}:{InvId}:{Password2}:Shp_user={USER_ID}")
raw = f"{OUT_SUM}:{INV_ID}:{PASSWORD2}"
SIGN = hashlib.md5(raw.encode("utf-8")).hexdigest()

payload = {
    "OutSum": OUT_SUM,
    "InvId": INV_ID,
    "SignatureValue": SIGN,
    # Shp_user НЕ добавляем
}

print(f"[TEST] POST → {VPS_BASE}/robokassa/result")
print("[TEST] Payload:", payload)

try:
    r = requests.post(
        f"{VPS_BASE}/robokassa/result",
        data=payload,
        timeout=15,
        verify=False  # самоподписанный сертификат — не проверяем
    )
    print("\n✅ Status:", r.status_code)
    print("Response:", r.text.strip()[:400])
except Exception as e:
    print("\n❌ Ошибка при запросе:", e)

# --- Проверка Supabase (если заданы ключи окружения) ---
try:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")

    if SUPABASE_URL and SUPABASE_KEY:
        headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}

        print("\n[TEST] Проверка таблицы payments ...")
        q = requests.get(
            f"{SUPABASE_URL}/rest/v1/payments",
            params={"select": "*", "external_id": f"eq.{INV_ID}"},
            headers=headers,
            timeout=15,
            verify=False
        )
        print("payments:", q.status_code, q.json())

        print("\n[TEST] Проверка таблицы user_subscriptions ...")
        q2 = requests.get(
            f"{SUPABASE_URL}/rest/v1/user_subscriptions",
            params={"select": "*", "user_id": f"eq.{USER_ID}"},
            headers=headers,
            timeout=15,
            verify=False
        )
        print("user_subscriptions:", q2.status_code, q2.json())
    else:
        print("\n[TEST] Supabase проверка пропущена (нет ключей окружения).")

except Exception as e:
    print("\n❌ Ошибка при обращении к Supabase:", e)

print("\n[TEST] ✅ Готово. Если воркер запущен — должен прийти пуш об активации подписки.")
