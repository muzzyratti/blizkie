# bot/utils/amplitude_logger.py

import os
import time
import uuid
import json
import requests

AMPLITUDE_API_KEY = os.getenv("AMPLITUDE_API_KEY")


def log_event(user_id: int,
              event_name: str,
              event_properties: dict = None,
              session_id: str = None):
    try:
        event = {
            "user_id": str(user_id),
            "event_type": event_name,
            "event_properties": event_properties or {},
            "time": int(time.time() * 1000),
            "insert_id": str(uuid.uuid4())
        }

        if session_id:
            event["session_id"] = session_id

        response = requests.post("https://api2.amplitude.com/2/httpapi",
                                 json={
                                     "api_key": AMPLITUDE_API_KEY,
                                     "events": [event]
                                 },
                                 timeout=3)
        response.raise_for_status()

    except Exception as e:
        print(f"[Amplitude] Failed to log event: {e}")


def set_user_properties(user_id: int, properties: dict):
    try:
        payload = {
            "api_key": AMPLITUDE_API_KEY,
            "user_id": str(user_id),
            "user_properties": {
                "$set": properties
            }
        }

        print("[Amplitude] Payload for identify:")
        print(json.dumps(payload, indent=2, ensure_ascii=False))

        response = requests.post("https://api2.amplitude.com/identify",
                                 json=payload,
                                 timeout=3)
        print("[Amplitude] Identify response:", response.status_code,
              response.text)
        response.raise_for_status()

    except Exception as e:
        print(f"[Amplitude] Failed to set user properties for {user_id}: {e}")
