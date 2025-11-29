"""
Настройка логирования.

Логи пишем:
- в консоль (StreamHandler)
- в файл в каталоге LOG_DIR (RotatingFileHandler с ротацией)

Пример формата строки лога:
2025-11-23 18:19:31.834 [MainThread] INFO main - Сообщение
"""

import logging
import os
import time
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()


class DotTimeFormatter(logging.Formatter):
    """
    Кастомный форматтер времени.

    Формат: YYYY-MM-DD HH:MM:SS.mmm
    """

    def formatTime(self, record, datefmt=None):
        t = time.localtime(record.created)
        datetime_str = time.strftime("%Y-%m-%d %H:%M:%S", t)
        return f"{datetime_str}.{int(record.msecs):03d}"


def setup_logging() -> None:
    """
    Инициализируем корневой логгер

    - создаем каталог LOG_DIR (если нет)
    - настраиваем консольный и файловый хендлеры
    - вешаем их на root-логгер
    """

    log_dir = os.getenv("LOG_DIR", "logs")
    log_file_name = os.getenv("LOG_FILE", "bot.log")
    log_encoding = os.getenv("LOG_ENCODING", "utf-8")
    log_max_bytes = int(os.getenv("LOG_MAX_BYTES", "5000000"))
    log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()

    # Уровень логирования (INFO / DEBUG / WARNING ...)
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Убедимся, что каталог для логов существует
    os.makedirs(log_dir, exist_ok=True)

    # Полный путь к файлу логов
    log_path = os.path.join(log_dir, log_file_name)

    fmt = "%(asctime)s [%(threadName)s] %(levelname)s %(name)s - %(message)s"

    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(DotTimeFormatter(fmt))

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding=log_encoding,
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(DotTimeFormatter(fmt))

    # Чистим старые хендлеры root-логгера, если они были
    logging.root.handlers.clear()

    logging.basicConfig(
        level=log_level,
        handlers=[console, file_handler],
    )
