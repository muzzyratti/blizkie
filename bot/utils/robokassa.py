import hashlib
import urllib.parse
import json
from datetime import datetime
from db.supabase_client import supabase

# ====== SETTINGS LOADER ======
def get_rk_settings() -> dict:
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

def get_paywall_settings() -> dict:
    row = (
        supabase.table("feature_flags")
        .select("value_json")
        .eq("key", "paywall_requisites")
        .maybe_single()
        .execute()
    )
    if not row or not row.data:
        raise RuntimeError("feature_flags: paywall_requisites not found")
    return row.data["value_json"]

# ====== FISCAL RECEIPT (Robokassa docs) ======
def _build_receipt(rk: dict, amount_rub: int | float) -> str:
    item = {
        "Name": rk.get("product_name", "Подписка"),
        "Quantity": 1,
        "Sum": float(amount_rub),
        "PaymentMethod": rk.get("payment_method", "full_payment"),
        "PaymentObject": rk.get("payment_object", "service"),
        "Tax": rk.get("tax", "none"),
    }
    receipt = {
        "Items": [item],
        "Taxation": rk.get("taxation", "usn_income"),
    }
    return json.dumps(receipt, ensure_ascii=False)

def _sign_for_link(login: str, out_sum: float, inv_id: int, password1: str, receipt_json: str | None) -> str:
    parts = [login, f"{out_sum:.2f}", str(inv_id)]
    if receipt_json:
        parts.append(receipt_json)
    parts.append(password1)
    raw = ":".join(parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()

# ====== PAYMENT LINK (Recurring + Success/Fail + Receipt) ======
def make_payment_link(*, user_id: int, amount_rub: int | float, description: str) -> tuple[str, int]:
    rk = get_rk_settings()
    login = rk["login"]
    password1 = rk["password1"]
    is_test = bool(rk.get("is_test", True))

    success_url = rk.get("success_url")
    fail_url = rk.get("fail_url")

    inv_id = int(datetime.now().timestamp())  # временный номер счёта

    receipt_json = _build_receipt(rk, amount_rub)
    sign = _sign_for_link(login, float(amount_rub), inv_id, password1, receipt_json)

    params = {
        "MerchantLogin": login,
        "OutSum": f"{float(amount_rub):.2f}",
        "InvId": inv_id,
        "Description": description,
        "Recurring": 1,
        "Receipt": urllib.parse.quote(receipt_json, safe=""),
        "SignatureValue": sign,
        "IsTest": "1" if is_test else "0",
        "Shp_user": str(user_id),
        "Culture": "ru",
        "Encoding": "utf-8",
    }
    if success_url:
        params["SuccessURL"] = success_url
    if fail_url:
        params["FailURL"] = fail_url

    query = urllib.parse.urlencode(params)
    return f"https://auth.robokassa.ru/Merchant/Index.aspx?{query}", inv_id
