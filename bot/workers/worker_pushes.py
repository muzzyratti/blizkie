import asyncio
import time
from datetime import datetime, timedelta, timezone

from db.supabase_client import supabase
from utils.logger import setup_logger
from db.feature_flags import get_flag

logger = setup_logger()

# Троттлинг на пустые логи
_QUIET_LOG_EVERY_SECONDS = 30
_last_empty_log_ts: datetime | None = None


# ==============================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================

def _utcnow():
    return datetime.now(timezone.utc)

def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _in_quiet_hours(now_utc: datetime, cfg: dict) -> bool:
    tz_offset = int(cfg.get("tz_offset_hours", 3))
    local = (now_utc + timedelta(hours=tz_offset)).time()

    start = int(cfg.get("quiet_hours", {}).get("start", 22))
    end = int(cfg.get("quiet_hours", {}).get("end", 9))

    if start <= end:
        return start <= local.hour < end
    return local.hour >= start or local.hour < end


def _next_quiet_end(now_utc: datetime, cfg: dict) -> datetime:
    tz_offset = int(cfg.get("tz_offset_hours", 3))
    local = now_utc + timedelta(hours=tz_offset)

    end_h = int(cfg.get("quiet_hours", {}).get("end", 9))
    target_local = local.replace(hour=end_h, minute=0, second=0, microsecond=0)

    if local.hour >= end_h:
        target_local = target_local + timedelta(days=1)

    return target_local - timedelta(hours=tz_offset)


def _global_cap_reached(now_utc: datetime, cap: int) -> bool:
    start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)

    res = (
        supabase.table("push_queue")
        .select("id", count="exact")
        .eq("status", "sent")
        .gte("sent_at", _iso(start))
        .lt("sent_at", _iso(end))
        .execute()
    )

    total = int(res.count or 0)
    return total >= cap


# ==============================
# ОСНОВНОЙ ОБРАБОТЧИК ПУША
# ==============================

async def _process_push(row: dict, cfg: dict, bot):
    """
    Отправка пуша — bot передаём извне!
    """

    push_id = row["id"]
    user_id = row["user_id"]
    push_type = row["type"]
    payload = row.get("payload") or {}

    now = _utcnow()

    # Quiet hours
    if _in_quiet_hours(now, cfg):
        logger.info(f"[push_worker] Quiet hours — skip push_id={push_id}")
        return

    # Global cap
    cap = int(cfg.get("global_daily_cap", 100))
    if _global_cap_reached(now, cap):
        logger.warning(f"[push_worker] Daily cap reached — skip push_id={push_id}")
        return

    # Формируем текст
    if push_type == "retention_nudge":
        step = payload.get("step")
        if step == 1:
            text = "Привет! Давно не заглядывали. Хотите увидеть новую идею?"
        elif step == 2:
            text = "Хэй! У нас есть еще идеи для вас. Глянем?"
        elif step == 3:
            text = "Кажется, вы пропали. Может, вернёмся к играм?"
        else:
            text = "Напоминание от Близких Игр!"

    elif push_type == "paywall_followup":
        step = payload.get("step")
        if step == 1:
            text = "Хотите интересных идей? Купите подписку."
        elif step == 2:
            text = "Мы подскажем как провести интересно время с ребёнком! Купите подписку."
        elif step == 3:
            text = "Подберите классную идею для игры с ребёнком на выходных! Купите подписку."
        elif step == 4:
            text = "Наше последнее напоминание! Купите подписку."
        else:
            text = "Хотите открыть больше карточек? Купите подписку."

    elif push_type == "premium_ritual":
        text = "Ваш пятничный ритуал: новая подборка идей!"

    elif push_type == "premium_welcome":
        # Новый тип пуша — после успешной оплаты
        amount = payload.get("amount_rub")
        text = (
            f"🎉 Подписка активирована!\n"
            f"Полный доступ к идеям открыт. "
            f"Спасибо за поддержку ❤️\n"
            f"(Оплата {amount} ₽)"
        )

    else:
        text = "Напоминание от Близких Игр!"

    # Отправка
    try:
        await bot.send_message(user_id, text)

        supabase.table("push_queue").update({
            "status": "sent",
            "sent_at": _iso(now)
        }).eq("id", push_id).execute()

        logger.info(f"[push_worker] ✅ Sent push_id={push_id} user={user_id}")

    except Exception as e:
        logger.warning(f"[push_worker] ❌ Failed push_id={push_id}: {e}")

        supabase.table("push_queue").update({
            "status": "failed",
            "sent_at": _iso(now)
        }).eq("id", push_id).execute()


# ==============================
# ФОНОВЫЙ ВОРКЕР
# ==============================

async def run_worker(bot):
    """
    bot — передаётся извне!
    """

    last_flags_load = 0
    cfg_cache = None

    while True:
        now = time.time()

        # обновляем флаги
        if cfg_cache is None or now - last_flags_load > 60:
            try:
                cfg_cache = get_flag("retention_policy", {})
                last_flags_load = now
            except Exception as e:
                logger.warning(f"[push_worker] Failed to load retention_policy: {e}")

        # чек очереди
        try:
            pending = (
                supabase.table("push_queue")
                .select("*")
                .eq("status", "pending")
                .lte("scheduled_at", datetime.utcnow().isoformat() + "Z")
                .order("scheduled_at", desc=False)
                .limit(10)
                .execute()
            )

            rows = pending.data or []

            if rows:
                logger.info(f"[push_worker] Found {len(rows)} pending pushes")

            for row in rows:
                await _process_push(row, cfg_cache, bot)

        except Exception as e:
            logger.warning(f"[push_worker] Process error: {e}")

        await asyncio.sleep(5)
