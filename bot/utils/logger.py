import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logger():
    """
    Универсальный логгер:
    - На Replit логирует только в консоль.
    - На VPS (если есть переменная окружения LOG_TO_FILE=true) — пишет и в файл logs/app.log.
    """
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger("blizkieigry")
    if logger.handlers:  # уже настроен
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    # консоль
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # при деплое на VPS включаешь запись в файл
    if os.getenv("LOG_TO_FILE", "false").lower() == "true":
        os.makedirs("logs", exist_ok=True)
        file_handler = RotatingFileHandler(
            "logs/app.log", maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
