# bot/utils/amplitude_logger.py

import os
import time
import uuid
import requests

AMPLITUDE_API_KEY = os.getenv("AMPLITUDE_API_KEY")
AMPLITUDE_URL_EVENT = "https://api2.amplitude.com/2/httpapi"

def log_event(user_id: int,
              event_name: str,
              event_properties: dict = None,
              session_id: str = None):
    try:
        if not AMPLITUDE_API_KEY:
            return

        event = {
            "user_id": str(user_id),
            "event_type": event_name,
            "event_properties": event_properties or {},
            "time": int(time.time() * 1000),
            "insert_id": str(uuid.uuid4())
        }

        if session_id:
            event["session_id"] = session_id

        requests.post(AMPLITUDE_URL_EVENT,
                      json={
                          "api_key": AMPLITUDE_API_KEY,
                          "events": [event]
                      },
                      timeout=2)
        # ошибки игнорируются намеренно
    except:
        pass  # молча проглатываем любые ошибки


def set_user_properties(user_id: int, properties: dict):
    # Заглушка: пока не работает корректно, не отправляем ничего
    return
