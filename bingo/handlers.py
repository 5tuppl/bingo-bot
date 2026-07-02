# -*- coding: utf-8 -*-
from __future__ import annotations
"""Обработчики Telegram. Библиотека pyTelegramBotAPI (telebot) выбрана
намеренно: она работает через `requests`, а значит проходит через
HTTP-прокси PythonAnywhere на бесплатном тарифе (в отличие от aiohttp/aiogram,
из-за которого и была ошибка `Cannot connect to host api.telegram.org:443`)."""

import html
import time

import telebot
from telebot.types import Message

from .game import BingoError, Storage, parse_numbers

# message_id списка -> chat_id (чтобы понимать, что ответ адресован списку)
_list_messages: dict[int, int] = {}

HELP_TEXT = (
    "🎲 <b>Бинго-бот</b>\n\n"
    "/бинго — начать новую игру (только админ)\n"
    "/бинго_закрыть — закрыть запись (только админ)\n"
    "/тираж — вытянуть одно число (только админ)\n"
    "/тираж5 — вытянуть сразу 5 чисел (только админ)\n"
    "/список — показать список участников\n"
    "/числа — показать выпавшие числа\n"
    "/бинго_стоп — завершить игру (только админ)\n\n"
    "Для участия ответьте на сообщение со списком "
    "5 числами от 1 до 99. Побеждает тот, чьи 5 чисел выпали первыми!"
)


def is_admin(bot: telebot.TeleBot, chat_id: int, user_id: int) -> bool:
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def display_name(msg: Message) -> str:
    user = msg.from_user
    if user.username:
        return "@" + user.username
    return html.escape(user.first_name or str(user.id))


def register_handlers(bot: telebot.TeleBot, storage: Storage):

    def send_list(chat_id: int):
        game = storage.get(chat_id)
        sent = bot.send_message(chat_id, game.render_list())
        _list_messages[sent.message_id] = chat_id

    # ---------- команды ----------

    @bot.message_handler(commands=["start", "help", "помощь"])
    def cmd_help(msg: Message):
        bot.send_message(msg.chat.id, HELP_TEXT, parse_mode="HTML")

    @bot.message_handler(commands=["бинго", "bingo"])
    def cmd_new(msg: Message):
        if msg.chat.type == "private":
            bot.reply_to(msg, "Бинго играется в группе. Добавьте меня в чат 🙂")
            return
        if not is_admin(bot, msg.chat.id, msg.from_user.id):
            bot.reply_to(msg, "Начать игру может только админ чата.")
            return
        try:
            storage.new_game(msg.chat.id)
        except BingoError as e:
            bot.reply_to(msg, str(e))
            return
        send_list(msg.chat.id)

    @bot.message_handler(commands=["бинго_закрыть", "close"])
    def cmd_close(msg: Message):
        game = storage.get(msg.chat.id)
        if not game or game.is_finished:
            bot.reply_to(msg, "Сейчас нет активной игры. Начните: /бинго")
            return
        if not is_admin(bot, msg.chat.id, msg.from_user.id):
            bot.reply_to(msg, "Закрыть запись может только админ чата.")
            return
        try:
            game.close_registration()
        except BingoError as e:
            bot.reply_to(msg, str(e))
            return
        storage.save()
        send_list(msg.chat.id)
        bot.send_message(msg.chat.id,
                         "Запись закрыта ❌ Начинаем розыгрыш! Команда: /тираж")

    def _do_draw(msg: Message, count: int):
        game = storage.get(msg.chat.id)
        if not game or game.is_finished:
            bot.reply_to(msg, "Сейчас нет активной игры. Начните: /бинго")
            return
        if not is_admin(bot, msg.chat.id, msg.from_user.id):
            bot.reply_to(msg, "Тянуть числа может только админ чата.")
            return
        for _ in range(count):
            try:
                number = game.draw_number()
            except BingoError as e:
                bot.reply_to(msg, str(e))
                break
            bot.send_message(msg.chat.id, f"🎱 Выпало число: <b>{number}</b>",
                             parse_mode="HTML")
            winners = game.check_winners()
            if winners:
                names = ", ".join(w.display for w in winners)
                bot.send_message(
                    msg.chat.id,
                    f"👑 <b>БИНГО!</b> Победител{'и' if len(winners) > 1 else 'ь'}: "
                    f"{names}\nВсе 5 чисел совпали! 🎉",
                    parse_mode="HTML")
                send_list(msg.chat.id)
                break
            if count > 1:
                time.sleep(1)  # пауза для драматизма при серийном тираже
        storage.save()

    @bot.message_handler(commands=["тираж", "draw"])
    def cmd_draw(msg: Message):
        _do_draw(msg, 1)

    @bot.message_handler(commands=["тираж5", "draw5"])
    def cmd_draw5(msg: Message):
        _do_draw(msg, 5)

    @bot.message_handler(commands=["список", "list"])
    def cmd_list(msg: Message):
        game = storage.get(msg.chat.id)
        if not game:
            bot.reply_to(msg, "Игры ещё не было. Начните: /бинго")
            return
        send_list(msg.chat.id)

    @bot.message_handler(commands=["числа", "drawn"])
    def cmd_drawn(msg: Message):
        game = storage.get(msg.chat.id)
        if not game:
            bot.reply_to(msg, "Игры ещё не было. Начните: /бинго")
            return
        bot.send_message(msg.chat.id, game.render_drawn())

    @bot.message_handler(commands=["бинго_стоп", "stop"])
    def cmd_stop(msg: Message):
        game = storage.get(msg.chat.id)
        if not game:
            bot.reply_to(msg, "Сейчас нет активной игры.")
            return
        if not is_admin(bot, msg.chat.id, msg.from_user.id):
            bot.reply_to(msg, "Завершить игру может только админ чата.")
            return
        storage.delete(msg.chat.id)
        bot.send_message(msg.chat.id, "Игра завершена. Спасибо за участие! 🏁")

    # ---------- запись через ответ на список ----------

    @bot.message_handler(
        func=lambda m: m.reply_to_message is not None
        and m.reply_to_message.message_id in _list_messages)
    def on_reply_to_list(msg: Message):
        _register(msg)

    # Фолбэк: после перезапуска бота словарь _list_messages пуст,
    # поэтому принимаем и ответ на любое сообщение бота с "Бинго Список".
    @bot.message_handler(
        func=lambda m: m.reply_to_message is not None
        and m.reply_to_message.from_user is not None
        and m.reply_to_message.from_user.is_bot
        and "Бинго Список" in (m.reply_to_message.text or ""))
    def on_reply_to_list_fallback(msg: Message):
        _register(msg)

    def _register(msg: Message):
        game = storage.get(msg.chat.id)
        if not game:
            bot.reply_to(msg, "Игры сейчас нет. Попросите админа: /бинго")
            return
        try:
            numbers = parse_numbers(msg.text)
            player = game.add_player(msg.from_user.id, display_name(msg), numbers)
        except BingoError as e:
            bot.reply_to(msg, "⚠️ " + str(e))
            return
        storage.save()
        bot.reply_to(
            msg,
            f"✅ {player.display} записан(а)! "
            f"Ваши числа: {', '.join(map(str, player.numbers))}")
        send_list(msg.chat.id)
