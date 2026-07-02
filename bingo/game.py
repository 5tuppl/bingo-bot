# -*- coding: utf-8 -*-
from __future__ import annotations
"""Чистая логика бинго-игры. Не зависит от Telegram API — легко тестируется."""

import json
import os
import random
import re
import threading
from dataclasses import dataclass, field, asdict

MIN_NUM = 1
MAX_NUM = 99
CARD_SIZE = 5  # лайн бинго — 5 чисел


class BingoError(Exception):
    """Базовая ошибка с сообщением для пользователя (на русском)."""


@dataclass
class Player:
    user_id: int
    display: str            # @username или имя
    numbers: list           # 5 чисел игрока
    is_winner: bool = False


@dataclass
class Game:
    chat_id: int
    is_open: bool = True            # открыта ли запись
    is_finished: bool = False
    drawn: list = field(default_factory=list)   # выпавшие числа по порядку
    players: dict = field(default_factory=dict)  # str(user_id) -> Player

    # ---------- регистрация ----------

    def add_player(self, user_id: int, display: str, numbers: list) -> Player:
        if self.is_finished:
            raise BingoError("Игра уже завершена. Дождитесь новой игры.")
        if not self.is_open:
            raise BingoError("Запись закрыта ❌ — новые участники не принимаются.")
        key = str(user_id)
        if key in self.players:
            raise BingoError("Вы уже участвуете! Менять числа нельзя.")
        validate_numbers(numbers)
        player = Player(user_id=user_id, display=display, numbers=sorted(numbers))
        self.players[key] = player
        return player

    def close_registration(self):
        if not self.players:
            raise BingoError("Нельзя закрыть запись: пока нет ни одного участника.")
        self.is_open = False

    # ---------- розыгрыш ----------

    def draw_number(self, rng: random.Random | None = None) -> int:
        """Вытянуть одно случайное число, которое ещё не выпадало."""
        if self.is_open:
            raise BingoError("Сначала закройте запись командой /бинго_закрыть.")
        if self.is_finished:
            raise BingoError("Игра уже завершена.")
        pool = [n for n in range(MIN_NUM, MAX_NUM + 1) if n not in self.drawn]
        if not pool:
            raise BingoError("Все числа уже выпали, а победителя нет — так не бывает 🙂")
        rng = rng or random
        number = rng.choice(pool)
        self.drawn.append(number)
        return number

    def check_winners(self) -> list:
        """Игроки, у которых ВСЕ 5 чисел выпали (и ещё не объявлены победителями)."""
        drawn_set = set(self.drawn)
        new_winners = []
        for player in self.players.values():
            if not player.is_winner and set(player.numbers) <= drawn_set:
                player.is_winner = True
                new_winners.append(player)
        if new_winners:
            self.is_finished = True
        return new_winners

    def numbers_left(self, player: Player) -> list:
        """Какие числа игрока ещё не выпали."""
        drawn_set = set(self.drawn)
        return [n for n in player.numbers if n not in drawn_set]

    # ---------- отображение ----------

    def render_list(self) -> str:
        status = "Открыт ✅" if self.is_open else "Закрыт ❌"
        lines = [f"🏆 Бинго Список: {status}"]
        if self.is_open:
            lines.append("Для записи ответьте на это сообщение "
                         f"{CARD_SIZE} числами в диапазоне {MIN_NUM}-{MAX_NUM}.")
        lines.append("")
        for i, player in enumerate(self.players.values(), start=1):
            crown = " 👑" if player.is_winner else ""
            nums = ", ".join(map(str, player.numbers))
            lines.append(f"{i}) {player.display}{crown} — [{nums}]")
        if not self.players:
            lines.append("Пока никто не записался.")
        return "\n".join(lines)

    def render_drawn(self) -> str:
        if not self.drawn:
            return "Ещё ни одно число не выпало."
        return "🎱 Выпавшие числа (" + str(len(self.drawn)) + "): " + \
            ", ".join(map(str, self.drawn))


# ---------- парсинг чисел из сообщения ----------

def parse_numbers(text: str) -> list:
    """Достать ровно 5 чисел 1-99 из текста ответа игрока."""
    tokens = re.findall(r"\d+", text or "")
    if len(tokens) != CARD_SIZE:
        raise BingoError(
            f"Нужно ровно {CARD_SIZE} чисел, а найдено {len(tokens)}. "
            f"Пример: 7 23 45 66 91")
    numbers = [int(t) for t in tokens]
    validate_numbers(numbers)
    return numbers


def validate_numbers(numbers: list):
    if len(numbers) != CARD_SIZE:
        raise BingoError(f"Нужно ровно {CARD_SIZE} чисел.")
    bad = [n for n in numbers if not (MIN_NUM <= n <= MAX_NUM)]
    if bad:
        raise BingoError(
            f"Числа {', '.join(map(str, bad))} вне диапазона {MIN_NUM}-{MAX_NUM}.")
    if len(set(numbers)) != CARD_SIZE:
        raise BingoError("Числа не должны повторяться.")


# ---------- хранилище (JSON на диске, по одной игре на чат) ----------

class Storage:
    """Простое потокобезопасное JSON-хранилище игр по chat_id."""

    def __init__(self, path: str = "games.json"):
        self.path = path
        self._lock = threading.Lock()
        self._games: dict[str, Game] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as f:
                raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            return
        for chat_id, g in raw.items():
            players = {k: Player(**p) for k, p in g.pop("players", {}).items()}
            self._games[chat_id] = Game(players=players, **g)

    def _save(self):
        data = {}
        for chat_id, game in self._games.items():
            d = asdict(game)
            data[chat_id] = d
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    def get(self, chat_id: int) -> Game | None:
        with self._lock:
            return self._games.get(str(chat_id))

    def new_game(self, chat_id: int) -> Game:
        with self._lock:
            existing = self._games.get(str(chat_id))
            if existing and not existing.is_finished:
                raise BingoError("В этом чате уже идёт игра. "
                                 "Завершите её командой /бинго_стоп.")
            game = Game(chat_id=chat_id)
            self._games[str(chat_id)] = game
            self._save()
            return game

    def save(self):
        with self._lock:
            self._save()

    def delete(self, chat_id: int):
        with self._lock:
            self._games.pop(str(chat_id), None)
            self._save()
