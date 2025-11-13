from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.amplitude_logger import log_event

cancel_subscription_router = Router()

_TEXT = (
    "❌ <b>Отмена подписки</b>\n\n"
    "Если вы оплачивали подписку, напишите мне — я вручную отключу автопродление. "
    "Мы уже внедряем автоматическую кнопку.\n\n"
    "📬 <b>Контакты:</b>\n"
    "• <a href='https://t.me/discoklopkov'>@discoklopkov</a>\n"
    "• Email: <code>aklopkov@gmail.com</code>\n\n"
    "Чтобы ускорить, можете отправить сообщение:\n"
    "«Прошу отменить автопродление для user_id <code>{user_id}</code>»"
)

def _kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Написать в Telegram", url="https://t.me/discoklopkov")]
    ])

@cancel_subscription_router.message(Command("cancel_subscription"))
async def cancel_subscription_cmd(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        _TEXT.format(user_id=user_id),
        reply_markup=_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    log_event(user_id, "subscription.cancel_info_shown.cmd")

@cancel_subscription_router.message(F.text == "/cancel_subscription")
async def cancel_subscription_text(message: types.Message):
    user_id = message.from_user.id
    await message.answer(
        _TEXT.format(user_id=user_id),
        reply_markup=_kb(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    log_event(user_id, "subscription.cancel_info_shown.text")
