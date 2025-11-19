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
    """
    Универсальная проверка подписи для Robokassa:
    - принимает OutSum/out_summ
    - принимает InvId/inv_id
    - не использует Shp-параметры
    - принимает SignatureValue или crc
    - НЕ меняет формат суммы (используем строку как есть!)
    """

    # 1. Достаём сумму (строка как есть)
    out_sum_raw = (
        params.get("OutSum")
        or params.get("out_summ")
        or params.get("outsumm")
        or params.get("outsum")
    )
    if out_sum_raw is None:
        print("🔴 verify_signature: no OutSum/out_summ in params")
        return False

    out_sum = str(out_sum_raw).strip()

    # 2. Достаём ID счета (строка как есть)
    inv_id_raw = (
        params.get("InvId")
        or params.get("inv_id")
        or params.get("InvoiceId")
        or params.get("invoice_id")
    )
    if inv_id_raw is None:
        print("🔴 verify_signature: no InvId/inv_id in params")
        return False

    inv_id = str(inv_id_raw).strip()

    # 3. Достаём подпись из Robokassa
    recv_sig = (
        params.get("SignatureValue")
        or params.get("signaturevalue")
        or params.get("signature")
        or params.get("crc")
        or ""
    )
    if not recv_sig:
        print("🔴 verify_signature: no SignatureValue/crc in params")
        return False

    recv_sig_up = str(recv_sig).upper()

    # 4. Формируем raw-строку для проверки: MD5(OutSum:InvId:Password2)
    raw = f"{out_sum}:{inv_id}:{password2}"
    calc = hashlib.md5(raw.encode()).hexdigest().upper()

    # Лог для дебага
    print("🧩 verify_signature debug:")
    print("   raw      =", raw)
    print("   calc_sig =", calc)
    print("   recv_sig =", recv_sig_up)

    return calc == recv_sig_up


@app.post("/robokassa/result")
async def robokassa_result(request: Request):
    rk = get_rk_settings()
    password2 = rk["password2"]

    params: dict = {}

    # 1) form-data / x-www-form-urlencoded
    try:
        form = await request.form()
        params = dict(form.items())
    except Exception:
        params = {}

    # 2) JSON
    if not params:
        try:
            params = await request.json()
        except Exception:
            params = {}

    # 3) RAW body: OutSum=...&InvId=...
    if not params:
        try:
            raw_body = (await request.body()).decode()
            tmp = {}
            for p in raw_body.split("&"):
                if "=" in p:
                    k, v = p.split("=", 1)
                    tmp[k] = v
            params = tmp
        except Exception:
            params = {}

    # Логирование для отладки
    print("🟡 Robokassa RESULT received:", params)
    print("🟡 Result headers:", request.headers)
    print("🟡 Content-Type:", request.headers.get("content-type"))

    if not verify_signature(params, password2):
        print("❌ Invalid signature")
        return Response("Invalid signature", status_code=400)

    # ---------- user_id ----------
    user_id_raw = (
        params.get("Shp_user")
        or params.get("shp_user")
        or params.get("UserId")
        or params.get("user_id")
    )

    if not user_id_raw:
        # Для recurring Shp_user может не приходить.
        # Для тестов/резерва берём test_user_id из feature_flags.
        test_uid = rk.get("test_user_id")
        if test_uid:
            user_id_raw = test_uid
        else:
            print("❌ No Shp_user in recurring payment and no fallback user_id set.")
            return Response("Missing user_id", status_code=400)

    user_id = int(user_id_raw)

    # ---------- InvId ----------
    inv_id_val = (
        params.get("InvId")
        or params.get("inv_id")
    )
    inv_id = str(inv_id_val)

    # ---------- сумма в рублях ----------
    out_sum_raw = (
        params.get("OutSum")
        or params.get("out_summ")
        or "0"
    )
    out_sum_rub = float(out_sum_raw)
    amount_rub = out_sum_rub

    now = datetime.now(timezone.utc)
    next_month = now + timedelta(days=30)
    email = params.get("EMail") or params.get("Email")

    # ---------- PAYMENTS ----------
    up = (
        supabase.table("payments").upsert(
            {
                "user_id": user_id,
                "provider": "robokassa",
                "kind": "subscription",
                "amount_rub": amount_rub,
                "currency": "RUB",
                "status": "paid",
                "external_id": inv_id,
                "raw": params,
                "paid_at": now.isoformat(),
                "payer_email": email,
            },
            on_conflict="provider,external_id",
        ).execute()
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

    # ---------- USER SUBSCRIPTIONS ----------
    plan_name = rk.get("plan_name", "monthly")
    supabase.table("user_subscriptions").upsert(
        {
            "user_id": user_id,
            "plan_name": plan_name,
            "auto_renew": True,
            "is_active": True,
            "renewed_at": now.isoformat(),
            "expires_at": next_month.isoformat(),
            "last_payment_id": payment_id,
            "payer_email": email,
        },
        on_conflict="user_id",
    ).execute()

    log_event(
        user_id,
        "subscription_payment_received",
        {
            "invoice_id": inv_id,
            "amount_rub": amount_rub,
            "payer_email": email,
        },
    )
    print("✅ Payment processed OK", inv_id)

    # МГНОВЕННЫЙ ПРИВЕТСТВЕННЫЙ ПУШ
    supabase.table("push_queue").insert(
        {
            "user_id": user_id,
            "type": "premium_welcome",
            "status": "pending",
            "scheduled_at": now.isoformat(),
            "payload": {"amount_rub": out_sum_rub},
        }
    ).execute()

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
        f"payment_ok_{inv_id}",
    )
    return HTMLResponse(content=html)


@app.get("/robokassa/fail")
async def robokassa_fail(request: Request):
    inv_id = request.query_params.get("InvId", "")
    html = _html_back_to_bot(
        "Оплата не завершена",
        "Если это ошибка — вернёмся в бот и попробуем ещё раз.",
        f"payment_fail_{inv_id}",
    )
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
