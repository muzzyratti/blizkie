from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse
from db.supabase_client import supabase
from utils.robokassa import get_rk_settings
from utils.amplitude_logger import log_event
from datetime import datetime, timedelta, timezone
import hashlib
from utils.push_scheduler import schedule_premium_ritual

app = FastAPI()
BOT_USERNAME = "blizkie_igry_bot"

def verify_signature(params: dict, password2: str) -> bool:
    out_sum = params.get("OutSum")
    inv_id = params.get("InvId")
    shp_params = {k: v for k, v in params.items() if k.lower().startswith("shp_")}
    shp_string = ":".join([f"{k}={shp_params[k]}" for k in sorted(shp_params)])
    raw = f"{out_sum}:{inv_id}:{password2}"
    if shp_string:
        raw = f"{raw}:{shp_string}"
    calc = hashlib.md5(raw.encode()).hexdigest().upper()
    recv = params.get("SignatureValue", "").upper()
    return calc == recv


@app.post("/robokassa/result")
async def robokassa_result(request: Request):
    rk = get_rk_settings()
    password2 = rk["password2"]

    form = await request.form()
    params = dict(form.items())
    print("🟡 Robokassa RESULT received:", params)

    if not verify_signature(params, password2):
        print("❌ Invalid signature")
        return Response("Invalid signature", status_code=400)

    user_id = int(params.get("Shp_user"))
    inv_id = str(params.get("InvId"))
    out_sum_rub = float(params.get("OutSum", 0.0))
    amount_cents = int(round(out_sum_rub * 100))

    now = datetime.now(timezone.utc)
    next_month = now + timedelta(days=30)

    # СОХРАНЯЕМ ПЛАТЁЖ
    up = (
        supabase.table("payments").upsert({
            "user_id": user_id,
            "provider": "robokassa",
            "kind": "subscription",
            "amount_cents": amount_cents,
            "currency": "RUB",
            "status": "paid",
            "external_id": inv_id,
            "raw": params,
            "paid_at": now.isoformat(),
        }, on_conflict="provider,external_id").execute()
    )
    if up.data and len(up.data):
        payment_id = up.data[0]["id"]
    else:
        sel = (
            supabase.table("payments")
            .select("id")
            .eq("external_id", inv_id)
            .maybe_single()
            .execute()
        )
        payment_id = sel.data["id"]

    # ОБНОВЛЯЕМ ПОДПИСКУ
    plan_name = rk.get("plan_name", "monthly")
    supabase.table("user_subscriptions").upsert({
        "user_id": user_id,
        "plan_name": plan_name,
        "auto_renew": True,
        "is_active": True,
        "renewed_at": now.isoformat(),
        "expires_at": next_month.isoformat(),
        "last_payment_id": payment_id,
    }, on_conflict="user_id").execute()

    log_event(user_id, "subscription_payment_received", {
        "invoice_id": inv_id,
        "amount_cents": amount_cents
    })
    print("✅ Payment processed OK", inv_id)

    # МГНОВЕННЫЙ ПРИВЕТСТВЕННЫЙ ПУШ
    supabase.table("push_queue").insert({
        "user_id": user_id,
        "type": "premium_welcome",
        "status": "pending",
        "scheduled_at": now.isoformat(),
        "payload": {"amount_rub": out_sum_rub}
    }).execute()

    # <<< ДОБАВЛЯЕМ СЮДА: ПОСТАНОВКА WEEKLY PREMIUM RITUAL >>>
    try:
        schedule_premium_ritual(user_id)
        print("🟢 Scheduled weekly premium_ritual for user:", user_id)
    except Exception as e:
        print("❌ Failed to schedule premium_ritual:", e)

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
    inv_id = request.query_params.get("InvId", "")
    html = _html_back_to_bot(
        "Оплата успешно принята",
        "Секунду… проверяю статус подписки.",
        f"payment_ok_{inv_id}"
    )
    return HTMLResponse(content=html)


@app.get("/robokassa/fail")
async def robokassa_fail(request: Request):
    inv_id = request.query_params.get("InvId", "")
    html = _html_back_to_bot(
        "Оплата не завершена",
        "Если это ошибка — вернёмся в бот и попробуем ещё раз.",
        f"payment_fail_{inv_id}"
    )
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
