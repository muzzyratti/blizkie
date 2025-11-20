import asyncio
import time
from datetime import datetime, timedelta, timezone

from db.supabase_client import supabase
from utils.logger import setup_logger
from db.feature_flags import get_flag
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from db.feature_flags import get_flag
from utils.amplitude_logger import log_event

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

    # ===== TEST MODE FOR PREMIUM RITUAL =====
    test_cfg = get_flag("premium_ritual_test", {}) or {}
    test_user = int(test_cfg.get("user_id", 0))
    interval = int(test_cfg.get("interval_sec", 0))

    if push_type == "premium_ritual" and test_user == user_id and interval > 0:
        logger.info(f"[push_worker] TEST premium_ritual bypass for user={user_id}")

        next_when = now + timedelta(seconds=interval)
        supabase.table("push_queue").insert({
            "user_id": user_id,
            "type": "premium_ritual",
            "status": "pending",
            "scheduled_at": _iso(next_when),
            "payload": {"weekly": False, "test": True},
        }).execute()

        log_event(
            user_id,
            "push_sent_premium_ritual",
            {
                "push_id": push_id,
                "type": push_type,
                "payload": payload
            }
        )

    # ----- Premium welcome bypass -----
    if push_type == "premium_welcome":
        logger.info(f"[push_worker] premium_welcome — bypass all limits for push_id={push_id}")
    else:
        if _in_quiet_hours(now, cfg):
            logger.info(f"[push_worker] Quiet hours — skip push_id={push_id}")
            return

        cap = int(cfg.get("global_daily_cap", 100))
        if _global_cap_reached(now, cap):
            logger.warning(f"[push_worker] Daily cap reached — skip push_id={push_id}")
            return

    markup = None

    # Формируем текст
    if push_type == "retention_nudge":
        step = payload.get("step")
        if step == 1:
            text = "Подберем быстро тёплую идею, чтобы вы провели с ребёнком пару минут вместе?"
        elif step == 2:
            text = "Сегодня идеальный день, чтобы добавить немного близости. Найдём новую игру на вечер с ребёнком?"
        elif step == 3:
            text = "Я тут для тебя и твоего ребёнка. Хочешь что-то лёгкое и тёплое сделать вместе? 😊"
        else:
            text = "Если захочешь — я всегда рядом. Подбросить идею для спокойного вечера?"

        kb = InlineKeyboardBuilder()
        kb.button(text="✨ Давай подберём идею!", callback_data="start_onboarding")
        markup = kb.as_markup()

    elif push_type == "retention_nudge_subscribers":
        step = payload.get("step")

        if step == 1:
            text = "Сегодня идеальный день, чтобы добавить немного близости. Найдём новую игру на вечер с ребёнком?"
        else:
            text = "Подберем быстро тёплую идею, чтобы вы провели с ребёнком пару минут вместе?"

        kb = InlineKeyboardBuilder()
        kb.button(text="✨ Давай подберём идею!", callback_data="start_onboarding")
        markup = kb.as_markup()

    elif push_type == "paywall_followup":
        step = payload.get("step")
        if step == 1:
            text = "Тут есть много простых и тёплых идей, которые делают ваши вечера ближе и спокойнее. Открой полный доступ — это правда меняет атмосферу дома 💛."
        elif step == 2:
            text = "Ты уже видел, как легко идеи помогают провести время с ребёнком. Хочешь больше? Мы собрали сотни игр специально для таких моментов ✨"
        elif step == 3:
            text = "Усталость, ритм, работа — всё съедает силы. Полный доступ помогает не думать, а просто давать ребёнку тепло через маленькие моменты близости."
        elif step == 4:
            text = "Последнее напоминание. Если чувствуешь, что хочешь больше спокойных и тёплых вечеров — подпишись. Это точно стоит того 💛."
        else:
            text = "Хотите открыть больше идей? Просто оплатите подписку."

        rk = get_flag("robokassa_keys", {})
        price = rk.get("price_rub", 490)

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text=f"💳 Оплатить подписку — {price} ₽", callback_data="open_paywall_direct"))
        kb.row(InlineKeyboardButton(text="Поддержка", url="https://t.me/discoklopkov"))
        markup = kb.as_markup()

    elif push_type == "premium_welcome":
        amount = payload.get("amount_rub")

        sub = (
            supabase.table("user_subscriptions")
            .select("expires_at")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        ).data

        expires_at_iso = sub.get("expires_at") if sub else None

        if expires_at_iso:
            dt = datetime.fromisoformat(expires_at_iso.replace("Z", "+00:00"))
            months = {
                1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",
                7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"
            }
            formatted_exp = f"{dt.day} {months[dt.month]} {dt.year} {dt.strftime('%H:%M:%S')} UTC"
            exp_line = f"\n\nПодписка продлена до {formatted_exp}"
        else:
            exp_line = ""

        text = (
            f"🎉 Подписка активирована!\n"
            f"Полный доступ к идеям открыт. Спасибо за поддержку ❤️\n"
            f"Получен платёж на сумму {amount} ₽"
            f"{exp_line}"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="✨ Давай подберём идею!", callback_data="start_onboarding")
        markup = kb.as_markup()

    elif push_type == "premium_ritual":
        text = (
            "🎉 Выходные рядом!\n\n"
            "Это лучшее время чтобы выбрать тёплую игру, "
            "которая подарит вам с ребёнком кусочек близости и радости.\n\n"
            "Готовы подобрать что-то особенное?"
        )

        kb = InlineKeyboardBuilder()
        kb.button(text="✨ Давай подберём идею!", callback_data="start_onboarding")
        markup = kb.as_markup()

    # ================================
    # НОВЫЙ ПУШ — INTERVIEW INVITE
    # ================================
    elif push_type == "interview_invite":
        try:
            text = (
                "Привет! Это Саша, создатель «Близких игр» 😊\n\n"
                "Вижу, что ты несколько раз пользовался ботом — спасибо тебе, это меня очень вдохновляет!\n"
                "Хочу попросить тебя о небольшой помощи.\n\n"
                "Давай пообщаемся 10–15 минут? Хочу услышать, что тебе нравится в боте, "
                "а что можно в нем улучшить.\n\n"
                "Если ок — нажми кнопку ниже и напиши мне 🙌"
            )

            photo_url = payload.get("photo_url")

            kb = InlineKeyboardBuilder()
            kb.row(
                InlineKeyboardButton(
                    text="💬 Написать Саше",
                    url="https://t.me/discoklopkov"
                )
            )
            markup = kb.as_markup()

            if photo_url:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_url,
                    caption=text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode="HTML"
                )

            supabase.table("push_queue").update({
                "status": "sent",
                "sent_at": _iso(now)
            }).eq("id", push_id).execute()

            logger.info(f"[push_worker] ✅ Sent interview_invite push_id={push_id} user={user_id}")

            # --- Amplitude event ---
            try:
                log_event(
                    user_id=user_id,
                    event_name="push_sent_interview_invite",
                    event_properties={
                        "push_id": push_id,
                        "photo_url": payload.get("photo_url"),
                    }
                )
            except Exception as e:
                logger.warning(f"[push_worker] ⚠️ Failed to send Amplitude event for interview_invite user={user_id}: {e}")

            return

        except Exception as e:
            logger.warning(f"[push_worker] ❌ Failed interview_invite push_id={push_id}: {e}")

            supabase.table("push_queue").update({
                "status": "failed",
                "sent_at": _iso(now)
            }).eq("id", push_id).execute()

            return

    else:
        text = "Бот Близких Игр тут. Хотите идей для тёплого вечера? Нажмите /start."

    # ----- ОТПРАВКА (ДЛЯ ВСЕХ ОСТАЛЬНЫХ ПУШЕЙ) -----
    try:
        if markup:
            await bot.send_message(user_id, text, reply_markup=markup)
        else:
            await bot.send_message(user_id, text)

        supabase.table("push_queue").update({
            "status": "sent",
            "sent_at": _iso(now)
        }).eq("id", push_id).execute()

        log_event(
            user_id,
            "push_sent",
            {
                "push_id": push_id,
                "type": push_type,
                "payload": payload
            }
        )

        logger.info(f"[push_worker] ✅ Sent push_id={push_id} user={user_id}")

        if push_type == "premium_ritual":
            try:
                from utils.push_scheduler import schedule_premium_ritual
                schedule_premium_ritual(user_id)
                logger.info(f"[push_worker] ⏭ Planned next premium_ritual for user={user_id}")
            except Exception as e:
                logger.warning(f"[push_worker] Failed to schedule next premium_ritual user={user_id}: {e}")

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
    last_flags_load = 0
    cfg_cache = None

    while True:
        now = time.time()

        if cfg_cache is None or now - last_flags_load > 60:
            try:
                cfg_cache = get_flag("retention_policy", {})
                last_flags_load = now
            except Exception as e:
                logger.warning(f"[push_worker] Failed to load retention_policy: {e}")

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
