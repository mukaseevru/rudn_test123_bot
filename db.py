"""
db.py — слой доступа к данным (SQLite через sqlite3, без ORM).

Особенности:
- Контекстный менеджер на каждую операцию (with _connect()) — гарантирует commit/rollback.
- PRAGMA:
    * WAL (журналирование вперёд) — меньше "database is locked";
    * busy_timeout — вежливое ожидание при блокировке.
- row_factory = sqlite3.Row — доступ к полям по именам, удобно для форматирования.

Схема: таблица notes (id, user_id, text, created_at)
+ индексы. Опционально: CHECK/UNIQUE для «приятных» ошибок.
"""

from __future__ import annotations

import sqlite3
import logging

from config import DB_PATH, DEFAULT_NOTIFY_HOUR

log = logging.getLogger(__name__)

# ---------------------------
# Низкоуровневое подключение
# ---------------------------

def _connect() -> sqlite3.Connection:
    """
    Открывает подключение к SQLite с разумными настройками для учебного бота.
    - timeout=5.0: подождать до 5 сек при блокировках;
    - PRAGMA foreign_keys=ON: соблюдение внешних ключей (на будущее);
    - PRAGMA journal_mode=WAL: снижает вероятность 'database is locked';
    - PRAGMA busy_timeout=5000: ожидание 5 сек при занятой БД;
    - row_factory=sqlite3.Row: строки как словари.
    """
    conn = sqlite3.connect(DB_PATH, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn
# Подробнее про WAL/busy_timeout и row_factory — в Л3.


# ---------------------------
# Инициализация схемы БД
# ---------------------------

def init_db() -> None:
    """
    Создаёт таблицы и индексы, если их нет.
    Включены простые ограничения качества данных: CHECK на длину, UNIQUE по (user_id, text).
    """
    schema = """
    CREATE TABLE IF NOT EXISTS notes (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        text       TEXT    NOT NULL CHECK(length(text) BETWEEN 1 AND 500),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, text) ON CONFLICT IGNORE
    );
    CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id);
    
    CREATE TABLE IF NOT EXISTS users (
        user_id        INTEGER PRIMARY KEY,
        sign           TEXT,
        notify_hour    INTEGER NOT NULL DEFAULT 9,
        subscribed     INTEGER NOT NULL DEFAULT 1,
        last_sent_date TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_users_hour ON users(notify_hour);
    CREATE INDEX IF NOT EXISTS idx_users_sent ON users(last_sent_date);
    
    -- Создаем таблицу с моделями и признаком активной модели
    CREATE TABLE IF NOT EXISTS models (
      id     INTEGER PRIMARY KEY,
      key    TEXT NOT NULL UNIQUE,
      label  TEXT NOT NULL,
      active INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0,1))
    );
    -- Ставим ограничение на поле active - только одна активная модель
    CREATE UNIQUE INDEX IF NOT EXISTS ux_models_single_active ON models(active) WHERE active=1;
    
    -- Добавляем список моделей в таблицу
    INSERT OR IGNORE INTO models(id, key, label, active) VALUES
        (1, 'deepseek/deepseek-chat-v3.1:free', 'DeepSeek V3.1 (free)', 1),
        (2, 'deepseek/deepseek-r1:free', 'DeepSeek R1 (free)', 0),
        (3, 'mistralai/mistral-small-24b-instruct-2501:free', 'Mistral Small 24b (free)', 0),
        (4, 'meta-llama/llama-3.1-8b-instruct:free', 'Llama 3.1 8B (free)', 0);
    """

    with _connect() as conn:
        conn.executescript(schema)
    log.info("DB initialized at %s", DB_PATH)
# Основано на структуре из Л3; опция CHECK/UNIQUE демонстрировалась на занятии.


# ---------------------------
# CRUD: заметки
# ---------------------------

def add_note(user_id: int, text: str) -> int | None:
    """
    Вставка заметки. Возвращает ID (lastrowid) или None при конфликте уникальности.
    """
    text = (text or "").strip()
    if not text:
        # Срабатывает и CHECK, но даём дружелюбную проверку здесь
        return None

    with _connect() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO notes(user_id, text) VALUES (?, ?)",
                (user_id, text)
            )
            return cur.lastrowid
        except sqlite3.IntegrityError as e:
            # Например, UNIQUE конфликт — одинаковая заметка у того же пользователя
            log.warning("IntegrityError on add_note: %s", e)
            return None
# Паттерн insert/lastrowid — как в Л3.


def list_notes(user_id: int, limit: int = 10) -> list[sqlite3.Row]:
    """
    Последние N заметок пользователя по id DESC.
    Ограничиваем limit в [1..50], чтобы не заспамить чат.
    """
    limit = max(1, min(int(limit or 10), 50))
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT id, text, created_at
            FROM notes
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        return cur.fetchall()
# SELECT + LIMIT — как в примерах Л3.


def search_notes(user_id: int, needle: str, limit: int = 10) -> list[sqlite3.Row]:
    """
    Поиск по подстроке (без учёта регистра).
    """
    needle = (needle or "").strip()
    if not needle:
        return []

    limit = max(1, min(int(limit or 10), 50))
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT id, text
            FROM notes
            WHERE user_id = ?
              AND text LIKE '%' || ? || '%' COLLATE NOCASE
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, needle, limit)
        )
        return cur.fetchall()
# LIKE с COLLATE NOCASE — рекомендация из Л3 по удобству поиска.


def update_note(user_id: int, note_id: int, new_text: str) -> bool:
    """
    Обновление текста заметки по (user_id, id).
    Возвращает True, если что-то реально изменилось.
    """
    new_text = (new_text or "").strip()
    if not new_text:
        return False

    with _connect() as conn:
        cur = conn.execute(
            "UPDATE notes SET text = ? WHERE user_id = ? AND id = ?",
            (new_text, user_id, note_id)
        )
        return cur.rowcount > 0
# rowcount важен для понимания факта изменения — см. Л3.


def delete_note(user_id: int, note_id: int) -> bool:
    """
    Удаление заметки по (user_id, id). Возвращает True при успехе.
    """
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM notes WHERE user_id = ? AND id = ?",
            (user_id, note_id)
        )
        return cur.rowcount > 0
# Обсуждалась опасность DELETE без WHERE — см. «страшилка» на семинаре/Л3.


def count_notes(user_id: int) -> int:
    """
    Количество заметок пользователя.
    """
    with _connect() as conn:
        cur = conn.execute(
            "SELECT COUNT(*) AS total FROM notes WHERE user_id = ?",
            (user_id,)
        )
        row = cur.fetchone()
        return int(row["total"] if row and "total" in row.keys() else 0)
# Простой COUNT(*) — как в блоке «статистика» Л3.


def stats_by_date(user_id: int, days: int = 7) -> list[sqlite3.Row]:
    """
    Возвращает до 'days' последних дат с количеством заметок:
    [ {d: 'YYYY-MM-DD', total: N}, ... ]
    """
    days = max(1, min(int(days or 7), 30))
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT date(created_at) AS d, COUNT(*) AS total
            FROM notes
            WHERE user_id = ?
            GROUP BY date(created_at)
            ORDER BY d DESC
            LIMIT ?
            """,
            (user_id, days)
        )
        return cur.fetchall()
# Группировка по датам + LIMIT — пример из Л3 (гистограмма).

# --------- МОДЕЛИ ---------
def list_models() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT id,key,label,active FROM models ORDER BY id").fetchall()
        return [{"id":r["id"], "key":r["key"], "label":r["label"], "active":bool(r["active"])} for r in rows]

def get_active_model() -> dict:
    with _connect() as conn:
        row = conn.execute("SELECT id,key,label FROM models WHERE active=1").fetchone()
        if row:
            return {"id":row["id"], "key":row["key"], "label":row["label"], "active":True}
        row = conn.execute("SELECT id,key,label FROM models ORDER BY id LIMIT 1").fetchone()
        if not row:
            raise RuntimeError("В реестре моделей нет записей")
        conn.execute("UPDATE models SET active=CASE WHEN id=? THEN 1 ELSE 0 END", (row["id"],))
        return {"id":row["id"], "key":row["key"], "label":row["label"], "active":True}

def set_active_model(model_id: int) -> dict:
    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        exists = conn.execute("SELECT 1 FROM models WHERE id=?", (model_id,)).fetchone()
        if not exists:
            conn.rollback()
            raise ValueError("Неизвестный ID модели")
        # 1) сначала снимаем активность со всех, у кого active=1
        conn.execute("UPDATE models SET active=0 WHERE active=1")
        # 2) затем включаем активность целевой модели
        conn.execute("UPDATE models SET active=1 WHERE id=?", (model_id,))
        conn.commit()
        return get_active_model()

def backup_to(path: str = "backup.db") -> None:
    """
    Делает простой бэкап текущей базы в файл path.
    """
    with sqlite3.connect(DB_PATH) as src, sqlite3.connect(path) as dst:
        src.backup(dst)
    log.info("SQLite backup created at %s", path)
# Приём backup() — из раздела про резервные копии на Л3.


# ---------- upsert/получение пользователя ----------
def ensure_user(user_id: int) -> None:
    """Гарантируем наличие строки пользователя с дефолтами."""
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users(user_id, notify_hour, subscribed) VALUES (?, ?, 1)",
            (user_id, DEFAULT_NOTIFY_HOUR)
        )

def get_user(user_id: int) -> Optional[sqlite3.Row]:
    with _connect() as conn:
        cur = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone()


# ---------- настройки профиля ----------
def set_sign(user_id: int, sign: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET sign = ? WHERE user_id = ?", (sign, user_id))

def set_notify_hour(user_id: int, hour: int) -> None:
    hour = max(0, min(int(hour), 23))
    with _connect() as conn:
        conn.execute("UPDATE users SET notify_hour = ? WHERE user_id = ?", (hour, user_id))

def set_subscribed(user_id: int, on: bool) -> None:
    val = 1 if on else 0
    with _connect() as conn:
        conn.execute("UPDATE users SET subscribed = ? WHERE user_id = ?", (val, user_id))


# ---------- рассылка: выборка и отметка отправки ----------
def list_due_users(today_str: str, hour: int) -> list[sqlite3.Row]:
    """
    Вернёт пользователей, кому надо отправить: подписан, час совпал, ещё не отправляли сегодня, знак задан.
    """
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT user_id, sign
            FROM users
            WHERE subscribed = 1
              AND sign IS NOT NULL
              AND notify_hour = ?
              AND (last_sent_date IS NULL OR last_sent_date <> ?)
            """,
            (hour, today_str)
        )
        return cur.fetchall()

def mark_sent_today(user_id: int, today_str: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE users SET last_sent_date = ? WHERE user_id = ?", (today_str, user_id))