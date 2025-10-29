import logging
import os
import sys

# Папка для логов
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

def is_log_type_enabled(name: str) -> bool:
    """
    Заглушка — всегда возвращает True
    """
    return True

def _make_handlers(filename: str):
    file_handler = logging.FileHandler(os.path.join(LOG_DIR, filename), encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    return file_handler, stream_handler

def setup_audio_diag_logger():
    """
    Настройка логгера audio_diag
    """
    logger = logging.getLogger("audio_diag")
    # Не дублировать хендлеры при повторном вызове
    if logger.handlers:
        return
    file_h, stream_h = _make_handlers("audio_diag.log")
    logger.addHandler(file_h)
    logger.addHandler(stream_h)
    logger.setLevel(logging.DEBUG)

def setup_player_logger():
    """
    Настройка логгера player
    """
    logger = logging.getLogger("player")
    # Не дублировать хендлеры при повторном вызове
    if logger.handlers:
        return
    file_h, stream_h = _make_handlers("player.log")
    logger.addHandler(file_h)
    logger.addHandler(stream_h)
    logger.setLevel(logging.DEBUG)