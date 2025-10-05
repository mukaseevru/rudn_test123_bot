"""
config.py — конфигурация проекта: переменные окружения, уровень логирования.
Проект: Telegram-бот (TeleBot) + SQLite (sqlite3) + python-dotenv.

Совет: .env не коммитим, .env занесён в .gitignore (см. методички S1/L2).
"""

from __future__ import annotations

import os
import logging
from dotenv import load_dotenv

# 1) Подтягиваем переменные окружения из .env
# (файл .env лежит рядом с проектом; токен и путь до БД — здесь)
load_dotenv()

# 2) Читаем переменные; DB_PATH имеет дефолт "bot.db"
TOKEN: str | None = os.getenv("TOKEN")
DB_PATH: str = os.getenv("DB_PATH", "bot.db")
DEFAULT_NOTIFY_HOUR = int(os.getenv("DEFAULT_NOTIFY_HOUR", "9"))

# 3) Уровень логирования настраиваем через .env (или оставляем INFO)
LOG_LEVEL_NAME = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_NAME, logging.INFO)

# 4) Базовая конфигурация логов для всего приложения
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# 5) Проверяем наличие токена сразу, чтобы не ловить странные ошибки позже
if not TOKEN:
    raise RuntimeError("В .env не найден TOKEN — получите токен у @BotFather и положите его в .env")

__all__ = ["TOKEN", "DB_PATH", "LOG_LEVEL"]
