# -*- coding: utf-8 -*-
"""Запуск через long polling — для своего ноутбука, VPS, Oracle Free и т.п.
НЕ подходит для PythonAnywhere free (там убивают вечные процессы) —
для него используйте bot_webhook.py."""

import os
import sys

import telebot

from bingo.game import Storage
from bingo.handlers import register_handlers

TOKEN = os.environ.get("BOT_TOKEN")
if not TOKEN:
    sys.exit("Ошибка: задайте переменную окружения BOT_TOKEN "
             "(токен от @BotFather).")

bot = telebot.TeleBot(TOKEN)
storage = Storage(os.environ.get("BINGO_DB", "games.json"))
register_handlers(bot, storage)

if __name__ == "__main__":
    print("Бинго-бот запущен (polling). Ctrl+C для остановки.")
    bot.infinity_polling(skip_pending=True)
