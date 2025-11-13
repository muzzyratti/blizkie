# utils/push_scheduler.py

from datetime import datetime, timedelta, timezone
from db.supabase_client import supabase
from utils.logger import setup_logger
from db.feature_flags import get_flag

logger = setup_logger()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _accumulate_seconds(cfg: dict, test_key: str) -> list[int]:
    """
    Накапливаем интервалы (в секундах) из retention_policy.delays_test_seconds[test_key].
    Например вход [20, 20, 20, 20] -> выход [20, 40, 60, 80].
    Если массива нет — дефолт [20, 40, 60, 80].
    """
    delays_map = cfg.get("delays_test_seconds") or {}
    raw = delays_map.get(test_key)
    if isinstance(raw, list) and raw:
        acc = 0
        out = []
        for d in raw:
            try:
                acc += int(d)
                out.append(acc)
            except Exception:
                continue
        if out:
            return out
    # дефолтная тест-цепочка
    return [20, 40, 60, 80]


def _schedule_many(user_id: int, push_type: str, at_list: list[datetime], payload: dict | None = None):
    if not at_list:
        return
    rows = []
    for at in at_list:
        rows.append(
            {
                "user_id": user_id,
                "type": push_type,
                "status": "pending",
                "scheduled_at": _iso(at),
                "payload": payload or {},
            }
        )
    supabase.table("push_queue").insert(rows).execute()


def clear_pending_pushes_for_user(user_id: int):
    supabase.table("push_queue").delete().eq("user_id", user_id).eq("status", "pending").execute()
    logger.info(f"[push_scheduler] 🧹 Cleared pending pushes for user={user_id}")


# =========================
# ПУБЛИЧНЫЕ API
# =========================

def schedule_retention_nudges(user_id: int):
    """
    Ставит цепочку retention_nudge после закрытия сессии.
    Тест: берём accumulate(seconds) из delays_test_seconds.retention_nudge.
    Прод: берём накапливаемые часы из nudge_delays_hours.
    """

    # предотвращаем повторное создание цепочки
    existing = (
        supabase.table("push_queue")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "retention_nudge")
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        logger.info(f"[push_scheduler] ⚠️ Retention chain exists, skip user={user_id}")
        return

    cfg = get_flag("retention_policy", {}) or {}

    # дефолты на случай пустого флага
    defaults = {
        "push_env": {"mode": "prod"},
        "nudge_delays_hours": [24, 72, 168, 336],  # 24ч, 72ч, 7д, 14д
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)

    mode = (cfg.get("push_env") or {}).get("mode", "prod")
    now = _utcnow()

    rows = []
    if mode == "test":
        offsets_sec = _accumulate_seconds(cfg, test_key="retention_nudge")
        for i, sec in enumerate(offsets_sec, start=1):
            when = now + timedelta(seconds=int(sec))
            rows.append(
                {
                    "user_id": user_id,
                    "type": "retention_nudge",
                    "payload": {"step": i},
                    "scheduled_at": _iso(when),
                    "status": "pending",
                }
            )
    else:
        hours = cfg.get("nudge_delays_hours") or [24, 72, 168, 336]
        acc_h = 0
        for i, h in enumerate(hours, start=1):
            try:
                acc_h += int(h)
            except Exception:
                continue
            when = now + timedelta(hours=acc_h)
            rows.append(
                {
                    "user_id": user_id,
                    "type": "retention_nudge",
                    "payload": {"step": i},
                    "scheduled_at": _iso(when),
                    "status": "pending",
                }
            )

    if rows:
        supabase.table("push_queue").insert(rows).execute()
        logger.info(f"[push_scheduler] ✅ Scheduled retention_nudge chain for user={user_id}")



def schedule_paywall_followup(user_id: int, *, reason: str | None = None):
    """
    Тест: берём accumulate(seconds) из delays_test_seconds.paywall_followup.
    Прод: берём накапливаемые часы из paywall_followup_hours.
    Если ключей нет — используем дефолты.

    Дефолты прод-цепочки:
      24ч, 72ч, 120ч (5д), 240ч (10д)
    """

    # предотвращаем повторное создание цепочки
    existing = (
        supabase.table("push_queue")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "paywall_followup")
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        logger.info(f"[push_scheduler] ⚠️ Paywall chain exists, skip user={user_id}")
        return

    cfg = get_flag("retention_policy", {}) or {}

    # дефолты на случай пустого флага
    defaults = {
        "push_env": {"mode": "prod"},
        "paywall_followup_hours": [24, 72, 120, 240],  # 1д, 3д, 5д, 10д
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)

    mode = (cfg.get("push_env") or {}).get("mode", "prod")
    now = _utcnow()

    rows = []
    if mode == "test":
        offsets_sec = _accumulate_seconds(cfg, test_key="paywall_followup")
        for i, sec in enumerate(offsets_sec, start=1):
            when = now + timedelta(seconds=int(sec))
            rows.append(
                {
                    "user_id": user_id,
                    "type": "paywall_followup",
                    "payload": {"step": i, "reason": reason},
                    "scheduled_at": _iso(when),
                    "status": "pending",
                }
            )
    else:
        hours = cfg.get("paywall_followup_hours") or [24, 72, 120, 240]
        acc_h = 0
        for i, h in enumerate(hours, start=1):
            try:
                acc_h += int(h)
            except Exception:
                continue
            when = now + timedelta(hours=acc_h)
            rows.append(
                {
                    "user_id": user_id,
                    "type": "paywall_followup",
                    "payload": {"step": i, "reason": reason},
                    "scheduled_at": _iso(when),
                    "status": "pending",
                }
            )

    if rows:
        supabase.table("push_queue").insert(rows).execute()
        logger.info(f"[push_scheduler] ✅ Scheduled paywall_followup chain for user={user_id}")

def schedule_premium_ritual(user_id: int):
    """
    КАЖДЫЙ ПЯТНИЧНЫЙ РИТУАЛ.
    В проде – ближайшая пятница 11:00 локально.
    В тесте – через delays_test_seconds.premium_ritual секунд.
    """

    cfg = get_flag("retention_policy", {}) or {}
    mode = (cfg.get("push_env") or {}).get("mode", "prod")

    now = _utcnow()

    # ===== TEST MODE =====
    if mode == "test":
        sec = int((cfg.get("delays_test_seconds", {}) or {}).get("premium_ritual", 50))
        when = now + timedelta(seconds=sec)

        # чистим старые
        supabase.table("push_queue").delete()\
            .eq("user_id", user_id)\
            .eq("type", "premium_ritual")\
            .eq("status", "pending")\
            .execute()

        supabase.table("push_queue").insert({
            "user_id": user_id,
            "type": "premium_ritual",
            "status": "pending",
            "scheduled_at": _iso(when),
            "payload": {"weekly": True}
        }).execute()

        logger.info(f"[push_scheduler] (TEST) premium_ritual set for user={user_id}")
        return

    # ===== PROD MODE =====
    # 1) Проверяем подписку
    sub = (
        supabase.table("user_subscriptions")
        .select("is_active, expires_at")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    ).data

    if not sub or not sub.get("is_active"):
        logger.info(f"[push_scheduler] No active subscription — skip premium_ritual user={user_id}")
        return

    # 2) Удаляем старые pending
    supabase.table("push_queue").delete()\
        .eq("user_id", user_id)\
        .eq("type", "premium_ritual")\
        .eq("status", "pending")\
        .execute()

    # 3) Расчёт ближайшей пятницы 11:00 локально
    tz_offset = int(cfg.get("tz_offset_hours", 3))
    local_now = now + timedelta(hours=tz_offset)

    weekday = local_now.weekday()  # 0=Mon ... 4=Fri
    add_days = (4 - weekday) % 7

    target_local = (
        local_now.replace(hour=11, minute=0, second=0, microsecond=0)
        + timedelta(days=add_days)
    )

    target_utc = target_local - timedelta(hours=tz_offset)

    # 4) Создаём новую задачу
    supabase.table("push_queue").insert({
        "user_id": user_id,
        "type": "premium_ritual",
        "status": "pending",
        "scheduled_at": _iso(target_utc),
        "payload": {"weekly": True},
    }).execute()

    logger.info(f"[push_scheduler] (PROD) premium_ritual scheduled {target_utc} user={user_id}")

