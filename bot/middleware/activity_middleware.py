# middleware/activity_middleware.py

from aiogram import BaseMiddleware
from aiogram.types import Update

from utils.session_tracker import mark_seen, new_session_if_needed


class ActivityMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):

        user_id = None

        if hasattr(event, "from_user") and event.from_user:
            user_id = event.from_user.id

        elif hasattr(event, "message") and event.message and event.message.from_user:
            user_id = event.message.from_user.id

        elif hasattr(event, "callback_query") and event.callback_query.from_user:
            user_id = event.callback_query.from_user.id

        if user_id:
            # Отметка активности
            mark_seen(user_id, source="tg")

            # Проверка — нужна ли новая сессия
            new_session_if_needed(user_id)

        return await handler(event, data)
