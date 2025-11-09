import os
from dotenv import load_dotenv

# 1. Загружаем базовый .env, где указано окружение
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

ENV = os.getenv("ENV", "dev")  # dev по умолчанию

# 2. Подгружаем нужный файл окружения
env_file = f".env.{ENV}"
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), env_file), override=True)

# 3. Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения")

# Контакт поддержки (телеграм-username без @). Если оставить None — кнопка не будет показана.
SUPPORT_USERNAME = "discoklopkov"  # или None