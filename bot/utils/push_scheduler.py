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

    # [FIX] 1. Если у юзера активна Paywall-воронка, обычный Retention не ставим (приоритет продажам)
    active_paywall = (
        supabase.table("push_queue")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "paywall_followup")
        .eq("status", "pending")
        .execute()
    )
    if active_paywall.data:
        logger.info(f"[push_scheduler] 🛡 Skip retention_nudge user={user_id}, active paywall chain exists")
        return
    
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
    # [FIX] Математика: берем абсолютные часы из конфига, без суммирования
        hours = cfg.get("nudge_delays_hours") or [24, 72, 168, 336]
    
        for i, h in enumerate(hours, start=1):
            try:
                offset_val = int(h)
                when = now + timedelta(hours=offset_val)
    
                rows.append({
                    "user_id": user_id, 
                    "type": "retention_nudge", 
                    "status": "pending",
                    "scheduled_at": _iso(when), 
                    "payload": {"step": i}
                })
            except Exception:
                continue

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

    # [FIX] 1. Убиваем обычный Retention, так как переходим к агрессивной продаже
    try:
        supabase.table("push_queue").delete()\
            .eq("user_id", user_id)\
            .eq("type", "retention_nudge")\
            .eq("status", "pending")\
            .execute()
        logger.info(f"[push_scheduler] 🔪 Killed retention_nudge for user={user_id} in favor of paywall")
    except Exception as e:
        logger.warning(f"[push_scheduler] Failed to cleanup retention_nudge: {e}")
    
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
    # [FIX] Математика абсолютная + дедупликация (чтобы не ставить два пуша на 120 час)
        hours = cfg.get("paywall_followup_hours") or [24, 72, 120, 240]
    
        seen_hours = set()
        step = 1
        for h in hours:
            try:
                val = int(h)
                if val in seen_hours:
                    continue # Пропускаем дубликаты времени
                seen_hours.add(val)
    
                when = now + timedelta(hours=val)
                rows.append({
                    "user_id": user_id, 
                    "type": "paywall_followup", 
                    "status": "pending",
                    "scheduled_at": _iso(when), 
                    "payload": {"step": step, "reason": reason}
                })
                step += 1
            except Exception:
                continue

    if rows:
        supabase.table("push_queue").insert(rows).execute()
        logger.info(f"[push_scheduler] ✅ Scheduled paywall_followup chain for user={user_id}")

def schedule_premium_ritual(user_id: int):
    """
    КАЖДЫЙ ПЯТНИЧНЫЙ РИТУАЛ.
    В проде – ближайшая пятница 13:00 локально.
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

    # 3) Ближайшая пятница 13:00 локально
    tz_offset = int(cfg.get("tz_offset_hours", 3))
    local_now = now + timedelta(hours=tz_offset)

    weekday = local_now.weekday()  # 0=Mon ... 4=Fri
    add_days = (4 - weekday) % 7

    target_local = (
        local_now.replace(hour=13, minute=0, second=0, microsecond=0)
        + timedelta(days=add_days)
    )

    # если уже после 13:00 — переносим на следующую неделю
    if target_local <= local_now:
        target_local += timedelta(days=7)

    target_utc = target_local - timedelta(hours=tz_offset)

    supabase.table("push_queue").insert({
        "user_id": user_id,
        "type": "premium_ritual",
        "status": "pending",
        "scheduled_at": _iso(target_utc),
        "payload": {"weekly": True},
    }).execute()

    logger.info(
        f"[push_scheduler] (PROD) premium_ritual scheduled {target_utc} user={user_id}"
    )

def schedule_retention_nudges_subscribers(user_id: int):
    """
    Цепочка для платных подписчиков.
    PROD:
      по умолчанию 2 и 10 дней (48 и 240 часов).
      можно переопределить retention_policy.subscriber_nudge_delays_hours.
    TEST:
      интервалы как у retention_nudge через delays_test_seconds.retention_nudge.
    """

    # не дублируем цепочку
    existing = (
        supabase.table("push_queue")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "retention_nudge_subscribers")
        .eq("status", "pending")
        .execute()
    )
    if existing.data:
        logger.info(f"[push_scheduler] ⚠️ Subscriber retention chain exists, skip user={user_id}")
        return

    cfg = get_flag("retention_policy", {}) or {}

    defaults = {
        "push_env": {"mode": "prod"},
        # 48ч (2 дня) и 240ч (10 дней)
        "subscriber_nudge_delays_hours": [48, 240],
    }
    for k, v in defaults.items():
        cfg.setdefault(k, v)

    mode = (cfg.get("push_env") or {}).get("mode", "prod")
    now = _utcnow()
    rows = []

    if mode == "test":
        # в тесте просто берём ту же схему, что и для retention_nudge
        offsets_sec = _accumulate_seconds(cfg, test_key="retention_nudge_subscribers")
        for i, sec in enumerate(offsets_sec, start=1):
            when = now + timedelta(seconds=int(sec))
            rows.append(
                {
                    "user_id": user_id,
                    "type": "retention_nudge_subscribers",
                    "payload": {"step": i},
                    "scheduled_at": _iso(when),
                    "status": "pending",
                }
            )
    else:
        # [FIX] Математика абсолютная. Дефолты: 3 дня (72ч) и 5 дней (120ч)
        hours = cfg.get("subscriber_nudge_delays_hours") or [72, 120]
    
        for i, h in enumerate(hours, start=1):
            try:
                val = int(h)
                when = now + timedelta(hours=val)
                rows.append({
                    "user_id": user_id, 
                    "type": "retention_nudge_subscribers", 
                    "status": "pending",
                    "scheduled_at": _iso(when), 
                    "payload": {"step": i}
                })
            except Exception:
                continue

    if rows:
        supabase.table("push_queue").insert(rows).execute()
        logger.info(f"[push_scheduler] ✅ Scheduled retention_nudge_subscribers chain for user={user_id}")

def schedule_interview_invite(user_id: int):
    """
    Однократный пуш-приглашение на интервью для премиум-юзера.

    Условия:
      - включён feature_flag "interview_invite"
      - у пользователя не было такого пуша раньше (ни pending, ни sent)
      - в таблице user_sessions у пользователя >= min_sessions (по флагу, дефолт 3)
      - опционально: есть хотя бы 1 просмотр L1 (seen_activities.level='l1')
    """
    cfg = get_flag("interview_invite", {}) or {}
    if not cfg.get("enabled", False):
        logger.info(f"[push_scheduler] interview_invite disabled for user={user_id}")
        return

    # 1) Уже есть такой пуш? (pending или sent) — не дублируем
    existing = (
        supabase.table("push_queue")
        .select("id")
        .eq("user_id", user_id)
        .eq("type", "interview_invite")
        .limit(1)
        .execute()
    )
    if existing.data:
        logger.info(f"[push_scheduler] interview_invite already exists for user={user_id}")
        return

    # 2) Кол-во сессий
    min_sessions = int(cfg.get("min_sessions", 3))
    sessions_res = (
        supabase.table("user_sessions")
        .select("session_id", count="exact")
        .eq("user_id", user_id)
        .execute()
    )
    total_sessions = int(sessions_res.count or 0)
    if total_sessions < min_sessions:
        logger.info(
            f"[push_scheduler] interview_invite skip user={user_id}, "
            f"sessions={total_sessions}, need>={min_sessions}"
        )
        return

    # 3) Минимум одна L1-карточка (если это требуется флагом)
    require_l1 = bool(cfg.get("require_l1", True))
    if require_l1:
        seen_res = (
            supabase.table("seen_activities")
            .select("activity_id", count="exact")
            .eq("user_id", user_id)
            .eq("level", "l1")
            .execute()
        )
        l1_count = int(seen_res.count or 0)
        if l1_count == 0:
            logger.info(
                f"[push_scheduler] interview_invite skip user={user_id}, "
                f"no L1 views"
            )
            return

    # 4) Ставим пуш "на сейчас"
    now = _utcnow()
    supabase.table("push_queue").insert({
        "user_id": user_id,
        "type": "interview_invite",
        "status": "pending",
        "scheduled_at": _iso(now),
        "payload": {
            "photo_url": "https://hcfnytsjrqtwstyivnrx.supabase.co/storage/v1/object/public/push_assets/interview_invite_1.jpeg"
        },
    }).execute()

    logger.info(f"[push_scheduler] ✅ interview_invite scheduled for user={user_id}")