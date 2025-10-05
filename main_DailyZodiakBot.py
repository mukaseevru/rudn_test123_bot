"""
main.py — DailyZodiakBot (развлекательный контент без внешних API).

Команды:
  /start                  — регистрация, выбор знака и часа
  /set_sign <знак>        — установить знак (или нажать кнопку с названием)
  /set_time <0..23>       — час утра/дня для рассылки (по времени сервера)
  /subscribe              — включить подписку
  /unsubscribe            — выключить подписку
  /me                     — мои настройки
  /today                  — выслать «гороскоп дня» прямо сейчас
  /signs                  — показать список знаков

Рассылка:
  - фоновый поток проверяет раз в минуту: кому отправить сейчас;
  - условие: subscribed=1, notify_hour == now.hour, last_sent_date != today.
"""

from __future__ import annotations
import logging
import threading
import time
import hashlib
from datetime import datetime, date

import telebot
from telebot import types

import db2 as db
from config2 import TOKEN, DEFAULT_NOTIFY_HOUR

log = logging.getLogger(__name__)

bot = telebot.TeleBot(TOKEN)
db.init_db()  # создаём схемы, если их нет

# ---------- справочник знаков: канон, синонимы, эмодзи ----------
CANON_SIGNS = [
    "овен", "телец", "близнецы", "рак", "лев", "дева",
    "весы", "скорпион", "стрелец", "козерог", "водолей", "рыбы"
]
SIGN_EMOJI = {
    "овен":"♈", "телец":"♉", "близнецы":"♊", "рак":"♋", "лев":"♌", "дева":"♍",
    "весы":"♎", "скорпион":"♏", "стрелец":"♐", "козерог":"♑", "водолей":"♒", "рыбы":"♓"
}
# Примитивные англ. синонимы — чтобы не спотыкались:
SIGN_ALIASES = {
    "aries":"овен", "taurus":"телец", "gemini":"близнецы", "cancer":"рак", "leo":"лев", "virgo":"дева",
    "libra":"весы", "scorpio":"скорпион", "sagittarius":"стрелец", "capricorn":"козерог", "aquarius":"водолей", "pisces":"рыбы"
}

def normalize_sign(text: str) -> str | None:
    t = (text or "").strip().lower()
    t = t.replace("ё", "е")
    if t in CANON_SIGNS:
        return t
    return SIGN_ALIASES.get(t)

def sign_keyboard() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    # 4 строки по 3 знака — компактно
    rows = [
        ["овен", "телец", "близнецы"],
        ["рак", "лев", "дева"],
        ["весы", "скорпион", "стрелец"],
        ["козерог", "водолей", "рыбы"]
    ]
    for r in rows:
        kb.row(*r)
    kb.row("/signs", "/me")
    return kb
# Используем ReplyKeyboard для быстрого выбора (паттерн из занятий по кнопкам) [oai_citation:7‡L2_Текст к лекции.pdf](file-service://file-6kQEVmhZuKhD1nBDo1XNnq)


# ---------- генерация «гороскопа» без API (детерминированно на (sign, date)) ----------
INTRO = [
    "Сегодня вас ждёт", "День сулит", "Утро принесёт", "В первой половине дня вероятно",
    "Хорошее время для", "Подходящий момент для"
]
FOCUS = ["работы", "личных дел", "общения", "обучения", "творчества", "маленьких поездок"]
ADVICE = [
    "действуйте спокойно и без спешки", "обратите внимание на детали", "держите курс и не отвлекайтесь",
    "не спорьте из принципа", "подумайте о пользе привычек", "не бойтесь попросить помощи"
]
LUCK = [
    "удача на вашей стороне", "окружающие настроены дружелюбно", "случай поможет тем, кто готов",
    "небольшой риск себя оправдает", "поддержка придёт вовремя", "день подойдёт для новых начал"
]
COLOR = ["синий", "зелёный", "жёлтый", "красный", "фиолетовый", "белый", "оранжевый"]
NUMBER = [3, 4, 5, 6, 7, 8, 9]

def _pick(seq: list, seed: bytes, salt: str) -> str:
    h = hashlib.md5(seed + salt.encode("utf-8")).hexdigest()
    idx = int(h, 16) % len(seq)
    return str(seq[idx])

def make_daily_text(sign: str, for_date: date) -> str:
    """
    Генерирует 3–4 коротких фразы и пару «фишек» (цвет, число).
    Детерминированно для (sign, date) — без внешних API.
    """
    iso = for_date.isoformat().encode("utf-8")
    sgn = sign.encode("utf-8")
    intro = _pick(INTRO, sgn+iso, ":intro")
    focus = _pick(FOCUS, sgn+iso, ":focus")
    advice = _pick(ADVICE, sgn+iso, ":advice")
    luck = _pick(LUCK, sgn+iso, ":luck")
    color = _pick(COLOR, sgn+iso, ":color")
    number = _pick(NUMBER, sgn+iso, ":num")

    emoji = SIGN_EMOJI.get(sign, "")
    return (
        f"{emoji} *{sign.capitalize()}* — {for_date.strftime('%Y-%m-%d')}\n"
        f"{intro} акцент на *{focus}*; {luck}. Советы: {advice}.\n\n"
        f"Счастливый цвет: *{color}*, число дня: *{number}*.\n"
        f"_Развлекательный контент._"
    )


# ---------- вспомогательные утилиты ----------
def user_mention(m: types.Message) -> str:
    u = m.from_user
    return f"{u.first_name or ''}".strip() or "друг"

def parse_hour(token: str) -> int | None:
    try:
        h = int(token)
        return h if 0 <= h <= 23 else None
    except Exception:
        return None


# ---------- команды ----------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message: types.Message) -> None:
    db.ensure_user(message.from_user.id)
    text = (
        "Привет! Я пришлю *гороскоп дня* без всяких API — для настроения.\n\n"
        "Сначала выбери знак и час отправки:\n"
        "• /set_sign <знак>  или нажми кнопку со знаком\n"
        "• /set_time <0..23> час (по времени сервера)\n\n"
        "Полезное:\n"
        "• /today — прислать на сегодня\n"
        "• /subscribe и /unsubscribe\n"
        "• /me — показать мои настройки\n"
        "• /signs — список знаков\n"
    )
    bot.send_message(message.chat.id, text, reply_markup=sign_keyboard(), parse_mode="Markdown")


@bot.message_handler(commands=["signs"])
def cmd_signs(message: types.Message) -> None:
    lines = [f"{SIGN_EMOJI[s]} {s.capitalize()}" for s in CANON_SIGNS]
    bot.reply_to(message, "Доступные знаки:\n" + "\n".join(lines))


@bot.message_handler(commands=["set_sign"])
def cmd_set_sign(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Формат: /set_sign <знак>  (например: /set_sign лев)")
        return
    s = normalize_sign(parts[1])
    if not s:
        bot.reply_to(message, "Не узнал знак. Напиши один из: " + ", ".join(CANON_SIGNS))
        return
    db.ensure_user(message.from_user.id)
    db.set_sign(message.from_user.id, s)
    bot.reply_to(message, f"Знак сохранён: {SIGN_EMOJI[s]} {s.capitalize()}")


@bot.message_handler(commands=["set_time"])
def cmd_set_time(message: types.Message) -> None:
    parts = message.text.split(maxsplit=1)
    hour = parse_hour(parts[1]) if len(parts) == 2 else None
    if hour is None:
        bot.reply_to(message, "Формат: /set_time <час 0..23>  (например: /set_time 9)")
        return
    db.ensure_user(message.from_user.id)
    db.set_notify_hour(message.from_user.id, hour)
    bot.reply_to(message, f"Час отправки сохранён: {hour}:00")


@bot.message_handler(commands=["subscribe"])
def cmd_subscribe(message: types.Message) -> None:
    db.ensure_user(message.from_user.id)
    db.set_subscribed(message.from_user.id, True)
    bot.reply_to(message, "Подписка включена. Я пришлю сообщение в заданный час.")


@bot.message_handler(commands=["unsubscribe"])
def cmd_unsubscribe(message: types.Message) -> None:
    db.ensure_user(message.from_user.id)
    db.set_subscribed(message.from_user.id, False)
    bot.reply_to(message, "Подписка выключена.")


@bot.message_handler(commands=["me"])
def cmd_me(message: types.Message) -> None:
    row = db.get_user(message.from_user.id)
    if not row:
        bot.reply_to(message, "Ещё не настроено. Используй /set_sign и /set_time.")
        return
    sign = row["sign"] or "не задан"
    hour = row["notify_hour"]
    sub = "включена" if row["subscribed"] else "выключена"
    bot.reply_to(
        message,
        f"Мои настройки:\nЗнак: {sign}\nЧас: {hour}:00\nПодписка: {sub}"
    )


@bot.message_handler(commands=["today"])
def cmd_today(message: types.Message) -> None:
    db.ensure_user(message.from_user.id)
    row = db.get_user(message.from_user.id)
    if not row or not row["sign"]:
        bot.reply_to(message, "Сначала /set_sign <знак>.")
        return
    txt = make_daily_text(row["sign"], date.today())
    bot.send_message(message.chat.id, txt, parse_mode="Markdown")


# ---------- обработка нажатий по клавиатуре со знаками ----------
@bot.message_handler(func=lambda m: (m.text or "").strip().lower() in CANON_SIGNS)
def kb_pick_sign(message: types.Message) -> None:
    s = (message.text or "").strip().lower()
    db.ensure_user(message.from_user.id)
    db.set_sign(message.from_user.id, s)
    bot.reply_to(message, f"Знак сохранён: {SIGN_EMOJI[s]} {s.capitalize()}")


# ---------- планировщик ежедневной отправки ----------
def scheduler_loop() -> None:
    log.info("Scheduler started")
    while True:
        now = datetime.now()               # время сервера
        today_str = now.strftime("%Y-%m-%d")
        hour = now.hour
        try:
            due = db.list_due_users(today_str, hour)
            for u in due:
                # Сгенерировать текст и отправить:
                txt = make_daily_text(u["sign"], now.date())
                try:
                    bot.send_message(u["user_id"], txt, parse_mode="Markdown")
                except Exception as e:
                    log.warning("Send failed to %s: %r", u["user_id"], e)
                # Отметить отправку за сегодня:
                db.mark_sent_today(u["user_id"], today_str)
        except Exception as e:
            log.exception("Scheduler error: %r", e)
        time.sleep(60)  # проверяем раз в минуту


def start_scheduler() -> None:
    t = threading.Thread(target=scheduler_loop, name="daily-scheduler", daemon=True)
    t.start()


# ---------- меню команд в клиенте (см. Л2) ----------
def setup_bot_commands() -> None:
    cmds = [
        types.BotCommand("start", "Начало и помощь"),
        types.BotCommand("set_sign", "Установить знак зодиака"),
        types.BotCommand("set_time", "Установить час отправки"),
        types.BotCommand("today", "Прислать на сегодня"),
        types.BotCommand("subscribe", "Включить подписку"),
        types.BotCommand("unsubscribe", "Выключить подписку"),
        types.BotCommand("me", "Мои настройки"),
        types.BotCommand("signs", "Список знаков"),
    ]
    bot.set_my_commands(cmds)


# ---------- точка входа ----------
if __name__ == "__main__":
    setup_bot_commands()        # удобство для пользователей [oai_citation:8‡L2_Текст к лекции.pdf](file-service://file-6kQEVmhZuKhD1nBDo1XNnq)
    start_scheduler()           # запускаем фоновую проверку
    bot.infinity_polling(skip_pending=True)  # запуск long polling (паттерн Л2/Л3) [oai_citation:9‡L2_Текст к лекции.pdf](file-service://file-6kQEVmhZuKhD1nBDo1XNnq) [oai_citation:10‡L3.pdf](file-service://file-TzQZFVK22mksuAGPBby5ME)
