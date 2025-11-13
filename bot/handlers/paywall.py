from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.amplitude_logger import log_event
from utils.push_scheduler import schedule_paywall_followup
from utils.paywall_guard import l0_views_count, _rules
from config import SUPPORT_USERNAME
from handlers.user_state import user_data
from db.supabase_client import supabase
from utils.robokassa import make_payment_link

paywall_router = Router()

# ============================================================
#   КЭШ + ЗАГРУЗКА ДАННЫХ PAYWALL ИЗ feature_flags
# ============================================================

_PAYWALL_CACHE = None

def get_paywall_settings():
    """
    Загружает данные из feature_flags.key = 'paywall_requisites'.
    Кэширует, чтобы не дергать Supabase каждый раз.
    """
    global _PAYWALL_CACHE
    if _PAYWALL_CACHE:
        return _PAYWALL_CACHE

    row = (
        supabase.table("feature_flags")
        .select("value_json")
        .eq("key", "paywall_requisites")
        .maybe_single()
        .execute()
    )

    if not row or not row.data:
        raise RuntimeError("feature_flags: key 'paywall_requisites' not found")

    _PAYWALL_CACHE = row.data["value_json"]
    return _PAYWALL_CACHE


# ============================================================
#   ТЕКСТЫ PAYWALL
# ============================================================

def _paywall_text(settings: dict) -> str:
    oferta = settings["oferta"]
    privacy = settings["privacy"]
    price = settings["price"]

    return (
        "🧩 Вы дошли до лимита бесплатной версии.\n\n"
        "Открыв подписку, вы получите неограниченный доступ к идеям — чтобы "
        "в любую секунду найти *идею, что сделать с ребёнком прямо сейчас*, "
        "под ваше время, энергию и возраст ребёнка.\n\n"
        "Мы регулярно добавляем новые идеи, чтобы тёплые моменты становились привычкой "
        "и делали семью ближе каждый день.\n\n"
        f"*{price} ₽ в месяц. Автопродление.*\n"
        f"Оплачивая, вы принимаете условия [Публичной оферты]({oferta}) "
        f"и [Политики конфиденциальности]({privacy})."
    )


def _requisites_text(settings: dict) -> str:
    fio = settings["fio"]
    inn = settings["inn"]
    email = settings["email"]
    tg = settings["tg"]
    oferta = settings["oferta"]
    privacy = settings["privacy"]
    pdn = settings["pdn"]

    return (
        "ℹ️ *Реквизиты:*\n\n"
        f"ФИО: {fio}\n"
        f"ИНН: {inn}\n"
        f"Email: {email}\n"
        f"Telegram: {tg}\n\n"
        "Документы:\n"
        f"• Договор оферты: {oferta}\n"
        f"• Политика конфиденциальности: {privacy}\n"
        f"• Политика обработки ПДн: {pdn}\n"
    )


# ============================================================
#   КЛАВИАТУРЫ
# ============================================================

def paywall_kb(settings: dict, can_continue_l0: bool):
    price = settings["price"]

    rows = [
        [InlineKeyboardButton(
            text=f"💳 Оплатить подписку — {price} ₽ в месяц",
            callback_data="subscribe"
        )],
        [InlineKeyboardButton(text="📄 Договор оферты", url=settings["oferta"])],
        [InlineKeyboardButton(text="ℹ️ Реквизиты", callback_data="pay_wall_requisites")],
    ]

    if SUPPORT_USERNAME:
        rows.append(
            [InlineKeyboardButton(
                text="💬 Поддержка",
                url=f"https://t.me/{SUPPORT_USERNAME}"
            )]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def requisites_kb(settings: dict):
    price = settings["price"]

    rows = [
        [InlineKeyboardButton(
            text=f"💳 Оплатить подписку — {price} ₽ в месяц",
            callback_data="subscribe"
        )],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="paywall_back")],
    ]

    if SUPPORT_USERNAME:
        rows.append(
            [InlineKeyboardButton(
                text="💬 Поддержка",
                url=f"https://t.me/{SUPPORT_USERNAME}"
            )]
        )

    return InlineKeyboardMarkup(inline_keyboard=rows)


# ============================================================
#   ОСНОВНАЯ ФУНКЦИЯ ОТПРАВКИ PAYWALL  (оставлена полностью)
# ============================================================

async def send_universal_paywall(msg_or_cb, reason: str, user_id: int, session_id: str | None):
    settings = get_paywall_settings()
    text = _paywall_text(settings)

    log_event(user_id, "paywall_shown", {"reason": reason, "session_id": session_id})

    ctx = user_data.setdefault(user_id, {})
    ctx["last_paywall_reason"] = reason

    rules = _rules() or {"l0": 15}
    can_continue = l0_views_count(user_id) < rules["l0"]

    kb = paywall_kb(settings, can_continue)

    if isinstance(msg_or_cb, types.CallbackQuery):
        await msg_or_cb.message.answer(
            text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True
        )
        await msg_or_cb.answer()
    else:
        await msg_or_cb.answer(
            text, reply_markup=kb, parse_mode="Markdown", disable_web_page_preview=True
        )


# ============================================================
#   НОВЫЕ ХЭНДЛЕРЫ
# ============================================================

@paywall_router.callback_query(F.data == "pay_wall_requisites")
async def on_pay_requisites(cb: types.CallbackQuery):
    settings = get_paywall_settings()

    await cb.message.edit_text(
        _requisites_text(settings),
        reply_markup=requisites_kb(settings),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await cb.answer()


@paywall_router.callback_query(F.data == "paywall_back")
async def on_paywall_back(cb: types.CallbackQuery):
    settings = get_paywall_settings()

    await cb.message.edit_text(
        _paywall_text(settings),
        reply_markup=paywall_kb(settings, can_continue_l0=False),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await cb.answer()


@paywall_router.callback_query(F.data == "subscribe")
async def on_subscribe(cb: types.CallbackQuery):
    """Генерим персональную ссылку Robokassa (Recurring + Receipt) и даём кнопку-URL."""
    settings = get_paywall_settings()
    price = float(settings["price"])
    user_id = cb.from_user.id

    log_event(user_id, "subscribe_click", {})

    pay_url, inv_id = make_payment_link(
        user_id=user_id,
        amount_rub=price,
        description="Подписка «Близкие игры», ежемесячно"
    )

    # клавиатура с URL-оплатой
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Перейти к оплате", url=pay_url)],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="paywall_back")]
        ]
    )

    await cb.message.answer(
        "Откроется защищённая страница Robokassa.\nПосле оплаты вас вернёт в бота.",
        reply_markup=kb
    )

@paywall_router.callback_query(F.data == "open_paywall_direct")
async def open_paywall_direct(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Генерируем ссылку Robokassa
    link, inv_id = make_payment_link(
        user_id=user_id,
        amount_rub=490,
        description="Подписка «Близкие Игры», ежемесячно"
    )

    text = (
        "Откроется защищённая страница Robokassa.\n"
        "После оплаты вас вернёт в бота."
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="💳 Перейти к оплате", url=link)
    markup = kb.as_markup()

    await callback.message.edit_text(text, reply_markup=markup)