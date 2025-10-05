"""
main.py — точка входа Telegram-бота (pyTelegramBotAPI / TeleBot).

Команды:
  /start                  — приветствие + список команд
  /note_add <текст>       — добавить заметку
  /note_list [N]          — показать последние N заметок (по умолчанию 10, максимум 50)
  /note_find <подстрока>  — поиск заметок по тексту (без учёта регистра)
  /note_edit <id> <текст> — изменить текст заметки
  /note_del <id>          — удалить заметку
  /note_count             — количество заметок
  /note_export            — выгрузка заметок в .txt
  /note_stats [days]      — статистика по датам (ASCII-гистограмма, по умолчанию 7 дней)

Замечания:
- Параметризация SQL всегда через "?" (никаких f-строк для SQL).
- Вся работа с БД — в модуле db.py.
"""

from __future__ import annotations

import os
import logging
from typing import Iterable

import telebot
from telebot import types

from config import TOKEN
import db

log = logging.getLogger(__name__)

# Создаём объект бота
bot = telebot.TeleBot(TOKEN)

# Инициализируем БД при старте процесса
db.init_db()

# ---------------------------
# Вспомогательные функции
# ---------------------------

def _fmt_notes(rows: Iterable) -> str:
    """
    Форматирует список заметок для ответа в чат.
    """
    if not rows:
        return "У вас пока нет заметок."
    # Каждая строка вида: "12: купить хлеб"
    return "\n".join(f"{r['id']}: {r['text']}" for r in rows)

def _parse_int(token: str) -> int | None:
    """
    Пытается распарсить целое число из строки (например, id или лимит).
    """
    try:
        return int(token.strip())
    except Exception:
        return None

def _bar(n: int) -> str:
    """
    ASCII-«полоска» для гистограммы. Ограничим до 30 символов,
    чтобы не растягивать сообщение.
    """
    n = max(0, min(int(n or 0), 30))
    return "·" * n

def _setup_bot_commands() -> None:
    """
    Регистрирует команды в меню клиента Telegram (удобно для новичков).
    """
    cmds = [
        types.BotCommand("start", "Приветствие и помощь"),
        types.BotCommand("note_add", "Добавить заметку"),
        types.BotCommand("note_list", "Список заметок"),
        types.BotCommand("note_find", "Поиск заметок"),
        types.BotCommand("note_edit", "Изменить заметку"),
        types.BotCommand("note_del", "Удалить заметку"),
        types.BotCommand("note_count", "Сколько заметок"),
        types.BotCommand("note_export", "Экспорт заметок в .txt"),
        types.BotCommand("note_stats", "Статистика по датам"),
    ]
    bot.set_my_commands(cmds)
# Паттерн set_my_commands — см. Л2 (удобное меню команд в клиенте).  [oai_citation:17‡L2_Текст к лекции.pdf](file-service://file-6kQEVmhZuKhD1nBDo1XNnq)


# ---------------------------
# Обработчики команд
# ---------------------------

@bot.message_handler(commands=["start", "help"])
def cmd_start(message: types.Message) -> None:
    """
    Поприветствовать пользователя и кратко описать команды.
    """
    text = (
        "Привет! Это заметочник на SQLite.\n\n"
        "Команды:\n"
        "  /note_add <текст>\n"
        "  /note_list [N]\n"
        "  /note_find <подстрока>\n"
        "  /note_edit <id> <текст>\n"
        "  /note_del <id>\n"
        "  /note_count\n"
        "  /note_export\n"
        "  /note_stats [days]\n"
    )
    bot.reply_to(message, text)


@bot.message_handler(commands=["note_add"])
def cmd_note_add(message: types.Message) -> None:
    """
    Добавить новую заметку: /note_add купить хлеб
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "Формат: /note_add <текст заметки>")
        return

    text = parts[1].strip()
    note_id = db.add_note(message.from_user.id, text)
    if note_id is None:
        # Либо пусто, либо UNIQUE-конфликт (такая заметка уже есть)
        bot.reply_to(message, "Не удалось добавить заметку. Возможно, такая уже есть или текст пустой.")
    else:
        bot.reply_to(message, f"Заметка #{note_id} добавлена.")


@bot.message_handler(commands=["note_list"])
def cmd_note_list(message: types.Message) -> None:
    """
    Показать последние N заметок: /note_list [N]
    """
    # Опциональный аргумент лимита
    parts = message.text.split(maxsplit=1)
    limit = _parse_int(parts[1]) if len(parts) == 2 else 10

    rows = db.list_notes(message.from_user.id, limit=limit or 10)
    bot.reply_to(message, _fmt_notes(rows))


@bot.message_handler(commands=["note_find"])
def cmd_note_find(message: types.Message) -> None:
    """
    Поиск заметок по подстроке: /note_find хлеб
    """
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        bot.reply_to(message, "Формат: /note_find <подстрока>")
        return

    needle = parts[1].strip()
    rows = db.search_notes(message.from_user.id, needle, limit=10)
    if not rows:
        bot.reply_to(message, "Ничего не найдено.")
    else:
        bot.reply_to(message, "\n".join(f"{r['id']}: {r['text']}" for r in rows))


@bot.message_handler(commands=["note_edit"])
def cmd_note_edit(message: types.Message) -> None:
    """
    Изменить текст заметки: /note_edit 12 купить молоко
    """
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        bot.reply_to(message, "Формат: /note_edit <id> <новый текст>")
        return

    note_id = _parse_int(parts[1])
    new_text = parts[2].strip() if len(parts) >= 3 else ""
    if not note_id or not new_text:
        bot.reply_to(message, "Формат: /note_edit <id> <новый текст>")
        return

    ok = db.update_note(message.from_user.id, note_id, new_text)
    bot.reply_to(message, "Готово." if ok else "Не найдено (проверьте id).")


@bot.message_handler(commands=["note_del"])
def cmd_note_del(message: types.Message) -> None:
    """
    Удалить заметку: /note_del 12
    """
    parts = message.text.split(maxsplit=1)
    note_id = _parse_int(parts[1]) if len(parts) == 2 else None
    if not note_id:
        bot.reply_to(message, "Формат: /note_del <id>")
        return

    ok = db.delete_note(message.from_user.id, note_id)
    bot.reply_to(message, "Удалено." if ok else "Не найдено (проверьте id).")


@bot.message_handler(commands=["note_count"])
def cmd_note_count(message: types.Message) -> None:
    """
    Количество заметок пользователя.
    """
    total = db.count_notes(message.from_user.id)
    bot.reply_to(message, f"У вас {total} заметок.")


@bot.message_handler(commands=["note_export"])
def cmd_note_export(message: types.Message) -> None:
    """
    Экспорт заметок пользователя в текстовый файл и отправка как документ.
    """
    rows = db.list_notes(message.from_user.id, limit=1000)
    if not rows:
        bot.reply_to(message, "Экспортировать нечего — заметок нет.")
        return

    fname = f"notes_{message.from_user.id}.txt"
    # Простая TSV-выгрузка: <id>\t<text>
    with open(fname, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(f"{r['id']}\t{r['text']}\n")

    # Отправляем файл и стараемся удалить после
    try:
        with open(fname, "rb") as f:
            bot.send_document(message.chat.id, f)
    finally:
        try:
            os.remove(fname)
        except OSError:
            pass
# Экспорт как в примере Л3 — «вау-эффект»: бот присылает файл пользователю.


@bot.message_handler(commands=["note_stats"])
def cmd_note_stats(message: types.Message) -> None:
    """
    ASCII-гистограмма: сколько заметок по дням.
    Пример: /note_stats 7
    """
    parts = message.text.split(maxsplit=1)
    days = _parse_int(parts[1]) if len(parts) == 2 else 7
    days = days if (days and days > 0) else 7

    rows = db.stats_by_date(message.from_user.id, days=days)
    if not rows:
        bot.reply_to(message, "Данных пока нет.")
        return

    lines = [f"{r['d']}: {_bar(r['total'])} {r['total']}" for r in rows]
    bot.reply_to(message, "Последние дни:\n" + "\n".join(lines))
# Группировка/визуализация — приём из Л3 (GROUP BY + ASCII-гистограмма).


# ---------------------------
# Запуск long polling
# ---------------------------

if __name__ == "__main__":
    _setup_bot_commands()  # удобное меню команд в Telegram-клиенте (Л2)
    log.info("Starting bot polling...")
    bot.infinity_polling(skip_pending=True)
