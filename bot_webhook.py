# -*- coding: utf-8 -*-
"""Запуск через webhook — рабочий способ для БЕСПЛАТНОГО PythonAnywhere.

Почему именно так (разбор ошибки со скриншота):
  `Cannot connect to host api.telegram.org:443 ssl:...`
  На free-тарифе PythonAnywhere исходящие соединения идут ТОЛЬКО через их
  HTTP-прокси и только к белому списку доменов. api.telegram.org в белом
  списке ЕСТЬ, но aiogram/aiohttp не умеет ходить через этот прокси
  автоматически — отсюда ошибка. Библиотека pyTelegramBotAPI использует
  `requests`, который прокси подхватывает сам. Плюс на free нельзя держать
  вечный polling-процесс, поэтому — webhook через Flask-приложение.

Настройка на PythonAnywhere (free):
  1. Web -> Add a new web app -> Flask -> укажите этот файл (переменная `app`).
  2. В разделе Web -> Environment variables (или в WSGI-файле) задайте:
       BOT_TOKEN     — токен от @BotFather
       WEBHOOK_HOST  — https://ВАШЛОГИН.pythonanywhere.com
  3. Откройте один раз https://ВАШЛОГИН.pythonanywhere.com/set_webhook
  4. Готово: Telegram сам присылает апдейты, вечный процесс не нужен.
"""

import os

import telebot
from flask import Flask, request, abort

from bingo.game import Storage
from bingo.handlers import register_handlers

TOKEN = os.environ.get("BOT_TOKEN", "")
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "").rstrip("/")
WEBHOOK_PATH = f"/webhook/{TOKEN}"

bot = telebot.TeleBot(TOKEN, threaded=False)  # threaded=False — важно для WSGI
storage = Storage(os.environ.get("BINGO_DB",
                                 os.path.expanduser("~/games.json")))
register_handlers(bot, storage)

app = Flask(__name__)


@app.route("/")
def index():
    return "Бинго-бот работает ✅"


@app.route("/set_webhook")
def set_webhook():
    if not TOKEN or not WEBHOOK_HOST:
        return "Задайте переменные окружения BOT_TOKEN и WEBHOOK_HOST", 500
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_HOST + WEBHOOK_PATH)
    return "Webhook установлен ✅"


@app.route(WEBHOOK_PATH, methods=["POST"])
def webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)
    update = telebot.types.Update.de_json(
        request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok"


if __name__ == "__main__":
    app.run(port=5000)
