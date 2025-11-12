import hashlib

OutSum = "100.00"
InvId = "12345"
Password2 = "K8YSV68WNkYzVSeh52YF"
user = "276358220"

raw = f"{OutSum}:{InvId}:{Password2}:Shp_user={user}"
sig = hashlib.md5(raw.encode()).hexdigest().upper()
print(sig)