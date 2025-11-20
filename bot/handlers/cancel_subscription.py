from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.amplitude_logger import log_event
from db.supabase_client import supabase

cancel_subscription_router = Router()

_TEXT = (
    "❌ <b>Отмена подписки</b>\n\n"
    "Если вы оплачивали подписку, напишите мне — я вручную отключу автопродление. "
    "Мы уже внедряем автоматическую кнопку.\n\n"
    "📬 <b>Контакты:</b>\n"
    "• <a href='https://t.me/discoklopkov'>@discoklopkov</a>\n"
    "• Email: <code>aklopkov@gmail.com</code>\n\n"
    "Чтобы ускорить, можете отправить сообщение:\n"
    "«Прошу отменить автопродление для: <code>{email}</code>»"
)

def _kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать в Telegram", url="https://t.me/discoklopkov")]
    ])

async def _get_user_email(user_id: int) -> str:
    """
    Возвращает email подписчика или "".
    Работает даже если нет строки, нет данных, res=None — ничего не падает.
    """
    try:
        res = (
            supabase
            .table("user_subscriptions")
            .select("payer_email")
            .eq("user_id", user_id)
            .maybe_single()
            .execute()
        )
    except Exception:
        return ""

    # res может быть None
    if not res:
        return ""

    data = getattr(res, "data", None)

    # data может быть None
    if not data:
        return ""

    email = data.get("payer_email")
    return email or ""


@cancel_subscription_router.message(Command("cancel_subscription"))
async def cancel_subscription_cmd(message: types.Message):
    user_id = message.from_user.id
    email = await _get_user_email(user_id)
    email_display = email if email else f"user_id {user_id}"

    await message.answer(
        _TEXT.format(email=email_display),
        reply_markup=_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    log_event(user_id, "subscription.cancel_info_shown.cmd")

@cancel_subscription_router.message(F.text == "/cancel_subscription")
async def cancel_subscription_text(message: types.Message):
    user_id = message.from_user.id
    email = await _get_user_email(user_id)
    email_display = email if email else f"user_id {user_id}"

    await message.answer(
        _TEXT.format(email=email_display),
        reply_markup=_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    log_event(user_id, "subscription.cancel_info_shown.text")
