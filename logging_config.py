import logging
import os
import sys

# Папка для логов
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def is_log_type_enabled(name: str) -> bool:
    """Заглушка — всегда возвращает True"""
    return True

def setup_audio_diag_logger():
    """Настройка логгера audio_diag"""
    logger = logging.getLogger("audio_diag")

    # файл
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "audio_diag.log"), encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)

    # консоль
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)

def setup_player_logger():
    """Настройка логгера player"""
    logger = logging.getLogger("player")

    file_handler = logging.FileHandler(os.path.join(LOG_DIR, "player.log"), encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.setLevel(logging.DEBUG)

