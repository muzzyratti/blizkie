import hashlib
import urllib.parse
import json
from db.supabase_client import supabase
from datetime import datetime, timedelta, timezone

# =============================
#   Чтение настроек Robokassa
# =============================

def get_rk_settings():
    row = (
        supabase.table("feature_flags")
        .select("value_json")
        .eq("key", "robokassa_keys")
        .maybe_single()
        .execute()
    )
    if not row or not row.data:
        raise RuntimeError("feature_flags: robokassa_keys not found")

    return row.data["value_json"]


# =============================
#   Генерация подписи для ссылки
# =============================

def make_payment_signature(login, out_sum, inv_id, password1, receipt=None):
    parts = [login, str(out_sum), str(inv_id)]
    if receipt:
        parts.append(receipt)
    parts.append(password1)

    raw = ":".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# =============================
#   Генерация ссылки на оплату
# =============================

def make_payment_link(user_id: int, price: int, description: str):
    rk = get_rk_settings()

    login = rk["login"]
    password1 = rk["password1"]
    test_mode = rk.get("is_test", True)

    inv_id = int(datetime.now().timestamp())  # временный invoice_id

    # Receipt (для чеков)
    receipt_dict = {
        "Items": [
            {
                "Name": rk.get("product_name", "Подписка"),
                "Quantity": 1,
                "Sum": price,
                "PaymentMethod": "full_payment",
                "PaymentObject": "service",
                "Tax": "none"
            }
        ],
        "Taxation": "usn_income"
    }

    receipt_json = json.dumps(receipt_dict, ensure_ascii=False)
    encoded_receipt = urllib.parse.quote(receipt_json)

    sign = make_payment_signature(
        login,
        price,
        inv_id,
        password1,
        receipt=receipt_json
    )

    params = {
        "MerchantLogin": login,
        "OutSum": price,
        "InvId": inv_id,
        "Description": description,
        "Recurring": 1,
        "Receipt": encoded_receipt,
        "SignatureValue": sign,
        "IsTest": "1" if test_mode else "0",
        "Shp_user": user_id  # Метка пользователя для удобства
    }

    query = urllib.parse.urlencode(params)
    return f"https://auth.robokassa.ru/Merchant/Index.aspx?{query}", inv_id
