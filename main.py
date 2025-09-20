# main.py
# Курс: «Введение в программирование для мобильных платформ: Telegram-бот с нуля»
# Стек: Python 3.11, pyTelegramBotAPI (TeleBot), long polling, .env (python-dotenv)
# В этом файле: базовые команды, reply/inline-кнопки, и погода по Москве через Open‑Meteo (без ключа).

from __future__ import annotations

import os
import logging
import json
from typing import List, Optional, Dict
from urllib.request import urlopen
from urllib.parse import urlencode
from urllib.error import URLError, HTTPError

from dotenv import load_dotenv
import telebot
from telebot import types

# ---------------------------------------------------------------------
# Конфигурация и инициализация
# ---------------------------------------------------------------------

# 1) Токен — обязательный параметр читаем из .env (TOKEN не коммитим) — см. практику курса.
#    (.env должен лежать в .gitignore, а пример .env.example — в репозитории)
#    Подробнее — на слайдах S1/L1. 
#    TOKEN=123456:ABC-DEF... (получить у @BotFather)
load_dotenv()
TOKEN = os.getenv("TOKEN")

if not TOKEN:
    raise RuntimeError("Не найден TOKEN в .env. Проверь файл .env и переменную TOKEN.")

# 2) Логи — помогут на семинарах и при разборе ошибок
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("tg-bot")

# 3) Инициализируем TeleBot с HTML-разметкой
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")


# ---------------------------------------------------------------------
# Клавиатуры
# ---------------------------------------------------------------------

def make_main_menu() -> types.ReplyKeyboardMarkup:
    """Главное меню (Reply Keyboard)."""
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("☀️ Погода Москва"),
        types.KeyboardButton("➕ Сложить числа"),
    )
    kb.add(
        types.KeyboardButton("ℹ️ О боте"),
        types.KeyboardButton("📌 Помощь"),
    )
    return kb


def make_like_inline() -> types.InlineKeyboardMarkup:
    """Пример inline-кнопок (callback)."""
    ikb = types.InlineKeyboardMarkup()
    ikb.add(
        types.InlineKeyboardButton("👍 Нравится", callback_data="like"),
        types.InlineKeyboardButton("👎 Не нравится", callback_data="dislike"),
    )
    return ikb


# ---------------------------------------------------------------------
# Утилиты
# ---------------------------------------------------------------------

def numbers_from_text(text: str) -> List[int]:
    """
    Достаёт целые числа из строки.
    Поддерживает знаки +/-, игнорирует прочие токены.
    Примеры: "2 3 10" -> [2, 3, 10], "/sum -5 x 7" -> [-5, 7]
    """
    nums: List[int] = []
    for token in text.split():
        t = token.strip()
        # пропускаем саму команду (начинается со '/')
        if t.startswith("/"):
            continue
        # простая проверка на целое со знаком
        if t.startswith(("+", "-")):
            body = t[1:]
        else:
            body = t
        if body.isdigit():
            try:
                nums.append(int(t))
            except ValueError:
                # на всякий случай — но сюда не зайдём при текущей проверке
                pass
    return nums


# ---------------------------------------------------------------------
# Интеграция: Погода (Open‑Meteo, без API-ключа)
# ---------------------------------------------------------------------

MOSCOW_COORDS = (55.7558, 37.6176)

OPEN_METEO_CODES: Dict[int, str] = {
    # Справочник погодных кодов Open‑Meteo (сокращён)
    0: "Ясно",
    1: "Преимущественно ясно",
    2: "Переменная облачность",
    3: "Пасмурно",
    45: "Туман",
    48: "Оседающий туман",
    51: "Мелкая морось", 53: "Морось", 55: "Сильная морось",
    56: "Ледяная морось", 57: "Сильная ледяная морось",
    61: "Слабый дождь", 63: "Дождь", 65: "Ливень",
    66: "Ледяной дождь", 67: "Сильный ледяной дождь",
    71: "Слабый снег", 73: "Снег", 75: "Сильный снег",
    77: "Снежные зёрна",
    80: "Кратковременный дождь (слаб.)",
    81: "Кратковременный дождь",
    82: "Ливневый дождь (сильн.)",
    85: "Кратковременный снег (слаб.)",
    86: "Кратковременный снег (сильн.)",
    95: "Гроза",
    96: "Гроза с градом (слаб.)",
    99: "Гроза с градом (сильн.)",
}

def fetch_moscow_weather() -> Optional[str]:
    """
    Запрашивает текущую погоду по Москве у Open‑Meteо (без ключа).
    Возвращает готовый для отправки текст или None при ошибке.
    """
    lat, lon = MOSCOW_COORDS
    params = {
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "timezone": "Europe/Moscow",
    }
    url = f"https://api.open-meteo.com/v1/forecast?{urlencode(params)}"

    try:
        with urlopen(url, timeout=6) as resp:
            data = json.load(resp)
    except HTTPError as e:
        logger.warning("Open-Meteo HTTPError: %s", e)
        return None
    except URLError as e:
        logger.warning("Open-Meteo URLError: %s", e)
        return None
    except Exception as e:
        logger.exception("Open-Meteo unknown error: %s", e)
        return None

    # Парсим "current"
    current: dict = data.get("current", {})
    if not current:
        return None

    t = current.get("temperature_2m")
    wcode = int(current.get("weather_code", -1))
    wind = current.get("wind_speed_10m")
    time_iso = current.get("time")

    desc = OPEN_METEO_CODES.get(wcode, f"Код погоды {wcode}")
    # Нарисуем небольшой эмодзи по типу погоды (очень упрощённо)
    icon = "☀️" if wcode in (0, 1) else "⛅" if wcode in (2,) else "☁️" if wcode in (3, 45, 48) else "🌧️" if wcode in (51, 53, 55, 61, 63, 65, 80, 81, 82) else "❄️" if wcode in (71, 73, 75, 77, 85, 86) else "⛈️" if wcode in (95, 96, 99) else "🌡️"

    # Человекочитаемое время
    when = time_iso.replace("T", " ") if isinstance(time_iso, str) else "—"

    return (
        f"{icon} <b>Погода в Москве (сейчас)</b>\n"
        f"Температура: <b>{t}°C</b>\n"
        f"Состояние: <b>{desc}</b>\n"
        f"Ветер: <b>{wind} м/с</b>\n"
        f"Обновлено: {when} (Europe/Moscow)"
    )


# ---------------------------------------------------------------------
# Хэндлеры команд
# ---------------------------------------------------------------------

@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message) -> None:
    logger.info("/start from %s", message.from_user.id if message.from_user else "unknown")
    bot.send_message(
        message.chat.id,
        "Привет! Я учебный бот.\n"
        "Нажимай кнопки ниже или смотри /help.",
        reply_markup=make_main_menu(),
    )


@bot.message_handler(commands=["help"])
def cmd_help(message: types.Message) -> None:
    logger.info("/help from %s", message.from_user.id if message.from_user else "unknown")
    help_text = (
        "<b>Команды</b>\n"
        "/start — главное меню\n"
        "/help — помощь\n"
        "/about — о боте\n"
        "/sum 2 3 10 — сумма целых чисел\n"
        "/echo текст — повторить текст\n"
        "/buttons — пример inline‑кнопок\n"
        "/max — <i>задание на дом</i> (см. описание в ответе)\n\n"
        "Или пользуйся кнопками внизу чата."
    )
    bot.send_message(message.chat.id, help_text, reply_markup=make_main_menu())


@bot.message_handler(commands=["about"])
def cmd_about(message: types.Message) -> None:
    # Простая информационная команда — была в S2
    bot.reply_to(
        message,
        "Я учебный бот курса: /start, /help, /sum, /echo, /buttons, /max (ДЗ).",
    )


@bot.message_handler(commands=["echo"])
def cmd_echo(message: types.Message) -> None:
    # Пример: разбор аргумента после команды (аналогично разбору /sum в S2)
    parts = message.text.split(maxsplit=1)
    arg = parts[1] if len(parts) > 1 else ""
    if not arg:
        bot.reply_to(message, "Использование: /echo текст")
    else:
        bot.reply_to(message, arg)


@bot.message_handler(commands=["sum"])
def cmd_sum(message: types.Message) -> None:
    """
    Суммирует целые числа из аргументов.
    Пример: /sum 2 3 10...-> Сумма: 15
    """
    nums = numbers_from_text(message.text)
    if not nums:
        # Запрашиваем числа в следующем сообщении (демо register_next_step_handler)
        msg = bot.reply_to(message, "Пришли числа через пробел (например: 2 3 10):")
        bot.register_next_step_handler(msg, _sum_next_step)
    else:
        bot.reply_to(message, f"Сумма: <b>{sum(nums)}</b>")


def _sum_next_step(message: types.Message) -> None:
    nums = numbers_from_text(message.text or "")
    if not nums:
        bot.reply_to(message, "Не нашёл целых чисел. Повтори ещё раз: примеры — 2 3 10 или -5 7")
        return
    bot.reply_to(message, f"Сумма: <b>{sum(nums)}</b>", reply_markup=make_main_menu())


@bot.message_handler(commands=["max"])
def cmd_max_stub(message: types.Message) -> None:
    """
    Заглушка под ДЗ: реализовать команду /max — вывести максимум из целых чисел.
    Ожидаемое поведение (пример): /max 2 5 3...-> Максимум: 5
    """
    bot.reply_to(
        message,
        "Эта команда — <b>задание на дом</b>.\n"
        "Сделай разбор аргументов по аналогии с /sum и выведи максимум.\n"
        "Пример: <code>/max 2 5 3</code> → <b>Максимум: 5</b>",
    )


@bot.message_handler(commands=["buttons"])
def cmd_buttons_demo(message: types.Message) -> None:
    """
    Демонстрация inline‑кнопок с callback_data.
    """
    bot.send_message(
        message.chat.id,
        "Нравится ли тебе этот пример кнопок?",
        reply_markup=make_like_inline(),
    )


@bot.callback_query_handler(func=lambda call: call.data in {"like", "dislike"})
def on_callback_like(call: types.CallbackQuery) -> None:
    if call.data == "like":
        bot.answer_callback_query(call.id, "Спасибо! 👍")
        bot.edit_message_text("Вы ответили: 👍 Нравится", call.message.chat.id, call.message.message_id)
    else:
        bot.answer_callback_query(call.id, "Понял! 👎")
        bot.edit_message_text("Вы ответили: 👎 Не нравится", call.message.chat.id, call.message.message_id)


# ---------------------------------------------------------------------
# Хэндлеры для кнопок главного меню (Reply Keyboard)
# ---------------------------------------------------------------------

@bot.message_handler(func=lambda m: (m.text or "").strip().lower() in {"ℹ️ о боте", "о боте"})
def on_about_button(message: types.Message) -> None:
    cmd_about(message)


@bot.message_handler(func=lambda m: (m.text or "").strip().lower() in {"📌 помощь", "помощь"})
def on_help_button(message: types.Message) -> None:
    cmd_help(message)


@bot.message_handler(func=lambda m: (m.text or "").strip().lower() in {"☀️ погода москва", "погода москва"})
def on_weather_button(message: types.Message) -> None:
    text = fetch_moscow_weather()
    if text is None:
        bot.reply_to(message, "Не удалось получить погоду. Попробуй ещё раз позже.")
        return
    bot.send_message(message.chat.id, text)


@bot.message_handler(func=lambda m: (m.text or "").strip().lower() in {"➕ сложить числа", "сложить числа"})
def on_sum_button(message: types.Message) -> None:
    # Такой же сценарий, как в /sum без аргументов
    msg = bot.reply_to(message, "Пришли целые числа через пробел (например: 2 3 10):")
    bot.register_next_step_handler(msg, _sum_next_step)


# ---------------------------------------------------------------------
# Точка входа (Long Polling)
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logger.info("Bot is starting (long polling)...")
    # skip_pending=True — пропускаем «залежавшиеся» апдейты, как рекомендуем на семинарах
    bot.infinity_polling(skip_pending=True, timeout=20)