import hashlib

# Вставь свои реальные данные Robokassa
Password2 = "K8YSV68WNkYzVSeh52YF"
OutSum = "100.00"
InvId = "12345"
user_id = "276358220"

raw = f"{OutSum}:{InvId}:{Password2}:Shp_user={user_id}"
SignatureValue = hashlib.md5(raw.encode()).hexdigest().upper()

print("SignatureValue:", SignatureValue)