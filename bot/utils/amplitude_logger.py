import os
import time
import uuid
import requests
from datetime import datetime
from utils.logger import setup_logger
from handlers.user_state import user_data

logger = setup_logger()

AMPLITUDE_API_KEY = os.getenv("AMPLITUDE_API_KEY")
AMPLITUDE_URL_EVENT = "https://api2.amplitude.com/2/httpapi"


def log_event(
    user_id: int,
    event_name: str,
    event_properties: dict | None = None,
    session_id: str | None = None,
    mutate_session: bool = True,   # ✅ добавлено
):
    """
    Отправляет событие в Amplitude и обновляет контекст сессии.
    """
    try:
        if mutate_session:
            ctx = user_data.setdefault(user_id, {})
            now = datetime.utcnow()
            ctx["last_seen"] = now
            ctx["actions_count"] = ctx.get("actions_count", 0) + 1
            if not ctx.get("first_event"):
                ctx["first_event"] = event_name
            ctx["last_event"] = event_name

        # локальная среда (Replit) без API-ключа
        if not AMPLITUDE_API_KEY:
            logger.info(f"[amplitude:SKIP] {event_name} user={user_id} props={event_properties}")
            return

        props = dict(event_properties or {})
        if session_id:
            props["bliz_session_id"] = session_id

        event = {
            "user_id": str(user_id),
            "event_type": event_name,
            "event_properties": props,
            "time": int(time.time() * 1000),
            "insert_id": str(uuid.uuid4()),
        }

        resp = requests.post(
            AMPLITUDE_URL_EVENT,
            json={"api_key": AMPLITUDE_API_KEY, "events": [event]},
            timeout=2,
        )

        if resp.status_code != 200:
            logger.error(f"[amplitude:ERROR] status={resp.status_code} body={resp.text}")
        else:
            logger.info(f"[amplitude:OK] {event_name} user={user_id} sid={session_id}")

    except Exception as e:
        logger.exception(f"[amplitude:EXCEPTION] Failed to send {event_name}")


def set_user_properties(user_id: int, properties: dict):
    """Заглушка под Identify API."""
    logger.info(f"[amplitude:IDENTIFY_STUB] user={user_id} props={properties}")
    return
