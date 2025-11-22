from aiogram import BaseMiddleware
from aiogram.types import Update
from utils.session_tracker import mark_seen, new_session_if_needed


class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):

        from_user = None

        # 1) message
        if hasattr(event, "message") and event.message:
            from_user = event.message.from_user

        # 2) callback
        elif hasattr(event, "callback_query") and event.callback_query:
            from_user = event.callback_query.from_user

        # 3) generic
        elif hasattr(event, "from_user"):
            from_user = event.from_user

        # ❗ Если нет юзера — игнор
        if not from_user:
            return await handler(event, data)

        user_id = from_user.id
        username = from_user.username

        # ❗❗ КЛЮЧ: если это сам бот — не трекать
        if from_user.is_bot:
            return await handler(event, data)

        # Только обычные пользователи попадают сюда
        mark_seen(user_id, source="tg", username=username)
        new_session_if_needed(user_id, source="tg", username=username)

        return await handler(event, data)
