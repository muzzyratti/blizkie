from fastapi import FastAPI, Request, Response
import hashlib
from db.supabase_client import supabase
from utils.robokassa import get_rk_settings
from utils.amplitude_logger import log_event
from datetime import datetime, timedelta, timezone
from fastapi.responses import HTMLResponse

app = FastAPI()

BOT_USERNAME = "blizkie_igry_bot"

# ============================================================
#  ХЕЛПЕР: Верификация подписи RESULTURL
# ============================================================

def verify_signature(params: dict, password2: str) -> bool:
    """
    Формула подписи:
    MD5(OutSum:InvId:Password2:Shp_xxx params sorted)
    """
    out_sum = params.get("OutSum")
    inv_id = params.get("InvId")

    # Дополнительные Shp_-параметры тоже должны быть включены
    shp_params = {k: v for k, v in params.items() if k.lower().startswith("shp_")}
    shp_string = ":".join([f"{k}={shp_params[k]}" for k in sorted(shp_params)])

    raw = f"{out_sum}:{inv_id}:{password2}"
    if shp_string:
        raw = f"{raw}:{shp_string}"

    calc = hashlib.md5(raw.encode()).hexdigest().upper()
    recv = params.get("SignatureValue", "").upper()

    return calc == recv


# ============================================================
#  POST /robokassa/result  (главный webhook)
# ============================================================

@app.post("/robokassa/result")
async def robokassa_result(request: Request):
    rk = get_rk_settings()
    password2 = rk["password2"]

    form = await request.form()
    params = dict(form.items())

    # Лог для отладки
    print("🟡 Robokassa RESULT received:", params)

    # Валидация подписи
    if not verify_signature(params, password2):
        print("❌ Invalid signature")
        return Response("Invalid signature", status_code=400)

    user_id = int(params.get("Shp_user"))
    inv_id = int(params.get("InvId"))
    out_sum = float(params.get("OutSum", 0.0))

    # ========================================================
    #   1. Записываем платёж (идемпотентно)
    # ========================================================
    existing = (
        supabase.table("payments")
        .select("*")
        .eq("invoice_id", inv_id)
        .maybe_single()
        .execute()
    )

    if not existing.data:
        supabase.table("payments").insert({
            "user_id": user_id,
            "invoice_id": inv_id,
            "amount": out_sum,
            "status": "paid",
            "raw_params": params,
        }).execute()

    # ========================================================
    #   2. Обновляем / создаём подписку
    # ========================================================
    now = datetime.now(timezone.utc)
    next_month = now + timedelta(days=30)

    sub = (
        supabase.table("user_subscriptions")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    if not sub.data:
        # создаём новую
        supabase.table("user_subscriptions").insert({
            "user_id": user_id,
            "is_active": True,
            "renewed_at": now.isoformat(),
            "expires_at": next_month.isoformat(),
            "last_payment_invoice": inv_id,
        }).execute()
    else:
        # обновляем существующую
        supabase.table("user_subscriptions").update({
            "is_active": True,
            "renewed_at": now.isoformat(),
            "expires_at": next_month.isoformat(),
            "last_payment_invoice": inv_id,
        }).eq("user_id", user_id).execute()

    # ========================================================
    #   3. Логируем в Amplitude
    # ========================================================
    log_event(user_id, "subscription_payment_received", {
        "invoice_id": inv_id,
        "amount": out_sum
    })

    print("✅ Payment processed OK", inv_id)

    # ========================================================
    #   4. Ответ Robokassa (строго по документации!)
    # ========================================================
    return Response(f"OK{inv_id}", media_type="text/plain")

def _html_back_to_bot(title: str, text: str, payload: str) -> str:
    deeplink = f"https://t.me/{BOT_USERNAME}?start={payload}"
    return f"""<!doctype html>
<html><head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title}</title>
<meta http-equiv="refresh" content="2;url={deeplink}">
</head>
<body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; padding:24px;">
  <h2>{title}</h2>
  <p>{text}</p>
  <p><a href="{deeplink}">Вернуться в бота</a></p>
</body></html>"""

@app.get("/robokassa/success")
async def robokassa_success(request: Request):
    q = dict(request.query_params)
    inv_id = q.get("InvId", "")
    html = _html_back_to_bot(
        "Оплата успешно принята",
        "Секунду… возвращаю в бот и проверяю статус подписки.",
        f"payment_ok_{inv_id}"
    )
    return HTMLResponse(content=html)

@app.get("/robokassa/fail")
async def robokassa_fail(request: Request):
    q = dict(request.query_params)
    inv_id = q.get("InvId", "")
    html = _html_back_to_bot(
        "Оплата не завершена",
        "Если это ошибка — вернёмся в бот и попробуем ещё раз.",
        f"payment_fail_{inv_id}"
    )
    return HTMLResponse(content=html)

