import os
from dotenv import load_dotenv
import telebot

load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Нет TOKEN в .env")

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Привет! Я здесь 🖐️\nЯ знаю команды: /start, /help")

@bot.message_handler(commands=['help'])
def help_cmd(message):
    bot.reply_to(message, "/start — начать, /help — подсказка")

if __name__ == "__main__":
    bot.infinity_polling(skip_pending=True)
