# -*- coding: utf-8 -*-
"""Юнит-тесты логики бинго. Запуск: python -m pytest tests/ -v"""

import os
import random
import tempfile

import pytest

from bingo.game import (
    BingoError, Game, Storage, parse_numbers, validate_numbers,
    MIN_NUM, MAX_NUM, CARD_SIZE,
)


# ---------- парсинг чисел ----------

class TestParseNumbers:
    def test_space_separated(self):
        assert parse_numbers("7 23 45 66 91") == [7, 23, 45, 66, 91]

    def test_comma_separated(self):
        assert parse_numbers("1, 2, 3, 4, 5") == [1, 2, 3, 4, 5]

    def test_mixed_text(self):
        assert parse_numbers("мои числа: 10 и 20, 30/40-50!") == [10, 20, 30, 40, 50]

    def test_too_few(self):
        with pytest.raises(BingoError, match="ровно 5"):
            parse_numbers("1 2 3 4")

    def test_too_many(self):
        with pytest.raises(BingoError, match="ровно 5"):
            parse_numbers("1 2 3 4 5 6")

    def test_out_of_range_high(self):
        with pytest.raises(BingoError, match="вне диапазона"):
            parse_numbers("1 2 3 4 100")

    def test_out_of_range_zero(self):
        with pytest.raises(BingoError, match="вне диапазона"):
            parse_numbers("0 2 3 4 5")

    def test_duplicates(self):
        with pytest.raises(BingoError, match="не должны повторяться"):
            parse_numbers("5 5 3 4 9")

    def test_empty(self):
        with pytest.raises(BingoError):
            parse_numbers("")

    def test_none(self):
        with pytest.raises(BingoError):
            parse_numbers(None)


class TestValidateNumbers:
    def test_boundaries_ok(self):
        validate_numbers([MIN_NUM, 2, 3, 4, MAX_NUM])  # не должно бросить

    def test_wrong_size(self):
        with pytest.raises(BingoError):
            validate_numbers([1, 2, 3])


# ---------- регистрация ----------

class TestRegistration:
    def make_game(self):
        return Game(chat_id=-100)

    def test_add_player(self):
        g = self.make_game()
        p = g.add_player(1, "@user", [9, 1, 5, 3, 7])
        assert p.numbers == [1, 3, 5, 7, 9]  # сортируются
        assert len(g.players) == 1

    def test_no_double_registration(self):
        g = self.make_game()
        g.add_player(1, "@user", [1, 2, 3, 4, 5])
        with pytest.raises(BingoError, match="уже участвуете"):
            g.add_player(1, "@user", [6, 7, 8, 9, 10])

    def test_two_players_same_numbers_allowed(self):
        g = self.make_game()
        g.add_player(1, "@a", [1, 2, 3, 4, 5])
        g.add_player(2, "@b", [1, 2, 3, 4, 5])
        assert len(g.players) == 2

    def test_closed_registration(self):
        g = self.make_game()
        g.add_player(1, "@a", [1, 2, 3, 4, 5])
        g.close_registration()
        with pytest.raises(BingoError, match="закрыта"):
            g.add_player(2, "@b", [6, 7, 8, 9, 10])

    def test_cannot_close_empty(self):
        g = self.make_game()
        with pytest.raises(BingoError, match="нет ни одного участника"):
            g.close_registration()

    def test_invalid_numbers_rejected(self):
        g = self.make_game()
        with pytest.raises(BingoError):
            g.add_player(1, "@a", [1, 2, 3, 4, 4])


# ---------- розыгрыш ----------

class TestDraw:
    def make_closed_game(self):
        g = Game(chat_id=-100)
        g.add_player(1, "@a", [1, 2, 3, 4, 5])
        g.add_player(2, "@b", [95, 96, 97, 98, 99])
        g.close_registration()
        return g

    def test_draw_before_close_forbidden(self):
        g = Game(chat_id=-100)
        g.add_player(1, "@a", [1, 2, 3, 4, 5])
        with pytest.raises(BingoError, match="закройте запись"):
            g.draw_number()

    def test_draw_in_range_and_unique(self):
        g = self.make_closed_game()
        rng = random.Random(42)
        seen = set()
        for _ in range(50):
            n = g.draw_number(rng)
            assert MIN_NUM <= n <= MAX_NUM
            assert n not in seen
            seen.add(n)
            if g.check_winners():
                break

    def test_winner_detected_exactly_when_all_five_drawn(self):
        g = self.make_closed_game()
        # вручную "вытягиваем" числа игрока @a по одному
        for n in [1, 2, 3, 4]:
            g.drawn.append(n)
            assert g.check_winners() == []  # 4 из 5 — ещё не победа
        g.drawn.append(5)
        winners = g.check_winners()
        assert len(winners) == 1
        assert winners[0].display == "@a"
        assert winners[0].is_winner
        assert g.is_finished

    def test_simultaneous_winners(self):
        g = Game(chat_id=-100)
        g.add_player(1, "@a", [1, 2, 3, 4, 5])
        g.add_player(2, "@b", [1, 2, 3, 4, 5])
        g.close_registration()
        g.drawn = [1, 2, 3, 4, 5]
        winners = g.check_winners()
        assert {w.display for w in winners} == {"@a", "@b"}

    def test_no_draw_after_finish(self):
        g = self.make_closed_game()
        g.drawn = [1, 2, 3, 4, 5]
        g.check_winners()
        with pytest.raises(BingoError, match="завершена"):
            g.draw_number()

    def test_numbers_left(self):
        g = self.make_closed_game()
        g.drawn = [1, 3]
        player = g.players["1"]
        assert g.numbers_left(player) == [2, 4, 5]

    def test_full_game_always_ends_with_winner(self):
        """Симуляция: при любом сиде игра заканчивается победителем."""
        for seed in range(20):
            rng = random.Random(seed)
            g = Game(chat_id=-100)
            pool = list(range(MIN_NUM, MAX_NUM + 1))
            for uid in range(1, 6):
                g.add_player(uid, f"@p{uid}", rng.sample(pool, CARD_SIZE))
            g.close_registration()
            winners = []
            while not winners:
                g.draw_number(rng)
                winners = g.check_winners()
            assert g.is_finished


# ---------- отображение ----------

class TestRender:
    def test_render_list_open(self):
        g = Game(chat_id=-100)
        g.add_player(1, "@admfisher", [1, 2, 3, 4, 5])
        text = g.render_list()
        assert "Открыт ✅" in text
        assert "1) @admfisher" in text
        assert "ответьте на это сообщение" in text

    def test_render_list_closed_with_crown(self):
        g = Game(chat_id=-100)
        g.add_player(1, "@winner", [1, 2, 3, 4, 5])
        g.close_registration()
        g.drawn = [1, 2, 3, 4, 5]
        g.check_winners()
        text = g.render_list()
        assert "Закрыт ❌" in text
        assert "@winner 👑" in text

    def test_render_drawn_empty(self):
        g = Game(chat_id=-100)
        assert "Ещё ни одно" in g.render_drawn()


# ---------- хранилище ----------

class TestStorage:
    def test_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "games.json")
            s1 = Storage(path)
            g = s1.new_game(-100)
            g.add_player(1, "@a", [1, 2, 3, 4, 5])
            g.close_registration()
            g.drawn = [1, 2]
            s1.save()

            s2 = Storage(path)  # перезагрузка с диска
            g2 = s2.get(-100)
            assert g2 is not None
            assert not g2.is_open
            assert g2.drawn == [1, 2]
            assert g2.players["1"].numbers == [1, 2, 3, 4, 5]

    def test_cannot_start_second_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Storage(os.path.join(tmp, "games.json"))
            s.new_game(-100)
            with pytest.raises(BingoError, match="уже идёт игра"):
                s.new_game(-100)

    def test_new_game_after_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Storage(os.path.join(tmp, "games.json"))
            g = s.new_game(-100)
            g.is_finished = True
            s.new_game(-100)  # не должно бросить

    def test_corrupted_file_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "games.json")
            with open(path, "w") as f:
                f.write("{сломанный json")
            s = Storage(path)  # не должно упасть
            assert s.get(-100) is None
