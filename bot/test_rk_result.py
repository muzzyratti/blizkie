import hashlib
import requests
import time
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

VPS_BASE = "https://194.54.156.170"
URL = f"{VPS_BASE}/robokassa/result"

PASSWORD2 = "G4Er4p0TlC52GocOmQVO"
OUT_SUM = "490.000000"
INV_ID = str(int(time.time()))
SIGN = hashlib.md5(f"{OUT_SUM}:{INV_ID}:{PASSWORD2}".encode()).hexdigest()

payload = {
    "OutSum": OUT_SUM,
    "out_summ": OUT_SUM,
    "InvId": INV_ID,
    "inv_id": INV_ID,
    "SignatureValue": SIGN,
    "crc": SIGN,
    "EMail": "test@example.com"
}

print("[TEST] Payload:", payload)

# === TEST 1 — FORM DATA ===
resp1 = requests.post(URL, data=payload, verify=False)
print("\n=== FORM DATA ===")
print(resp1.status_code, resp1.text)

# === TEST 2 — JSON ===
resp2 = requests.post(URL, json=payload, verify=False)
print("\n=== JSON ===")
print(resp2.status_code, resp2.text)

# === TEST 3 — RAW key=value ===
raw_body = "&".join([f"{k}={v}" for k, v in payload.items()])
resp3 = requests.post(
    URL,
    data=raw_body,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    verify=False
)
print("\n=== RAW BODY ===")
print(resp3.status_code, resp3.text)
