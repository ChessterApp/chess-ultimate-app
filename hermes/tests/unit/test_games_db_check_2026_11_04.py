"""The check of 04.11 on «any game from the database reaches the board» (HEAD e9161fd3), fixed by class.

Fresh sentences (283 true, 126 false, 39 targeted) and a live run with the real model found:
  * a theory line that starts like the loaded game and leaves it was read as the game told wrong (the Austrian
    Attack beside Kasparov – Topalov's Pirc), and so were the student's games and games of unknown players named
    with «в партии» («в партии против petr77», «Иванов – Петров, которую ты прислал»);
  * an empty position search counted only with «позиция» in the sentence; an earlier empty search only with
    «в прошлый раз»-words («как я уже говорил», «ту партию», «я проверял» were cut);
  * «I don't have access to the games database», «Я поискал в базе, но ничего не нашёл», "…so I'll tell it from
    memory" ("I'll" read as a player) passed; moves told with the piece in the instrumental («конём»), castling,
    «вторглась / поставили / отвели», the reply («…, а Синдаров в ответ съел слона на e2»), Kazakh and an
    impossible numbered move were not judged;
  * the red arrow of a cut sentence stayed on the board (the mark went out before its sentence was checked — the
    change that held marks lost marks of shown sentences and was taken back on 04.11, production behaviour kept);
    «Соблазнительно сыграть Nxf7 — так все и попадаются…» was read as advice, «после Nxf7 чёрные бьют на g2» as the
    knight's attack;
  * «загрузи третью из списка» loaded the fifth game, «а следующую?» the wrong one;
  * «задачку на вилку конём» put up a fork by the queen;
  * existing checks beside the loaded game: «1.e4 d5 2.exd5» (a Scandinavian) judged at move 2 of the game, «Ферзь на
    b6 был под боем» on the final position, «король белых прошёл с g1 на g5» as one move.
"""

import io
import json
from unittest.mock import patch

import chess
import chess.pgn
import pytest

from src import answer_check_db as acd
from src.answer_check import CheckContext, check_sentence, proposed_move
from src.game_list_ref import list_note, list_reference, shown_order
from src.sessions import Session

KT = """[Event "Hoogovens"]
[Date "1999.01.20"]
[White "Kasparov, Garry"]
[Black "Topalov, Veselin"]
[Result "1-0"]

1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3 Bg7 5.Qd2 c6 6.f3 b5 7.Nge2 Nbd7 8.Bh6 Bxh6 9.Qxh6 Bb7 10.a3 e5 11.O-O-O Qe7
12.Kb1 a6 13.Nc1 O-O-O 14.Nb3 exd4 15.Rxd4 c5 16.Rd1 Nb6 17.g3 Kb8 18.Na5 Ba8 19.Bh3 d5 20.Qf4+ Ka7 21.Rhe1 d4
22.Nd5 Nbxd5 23.exd5 Qd6 24.Rxd4 cxd4 25.Re7+ Kb6 26.Qxd4+ Kxa5 27.b4+ Ka4 28.Qc3 Qxd5 29.Ra7 Bb7 30.Rxb7 Qc4
31.Qxf6 Kxa3 32.Qxa6+ Kxb4 33.c3+ Kxc3 34.Qa1+ Kd2 35.Qb2+ Kd1 36.Bf1 Rd2 37.Rd7 Rxd7 38.Bxc4 bxc4 39.Qxh8 Rd3
40.Qa8 c3 41.Qa4+ Ke1 42.f4 f5 43.Kc1 Rd2 44.Qa7 1-0
"""
ST = """[Event "Tilburg"]
[Date "1991.10.??"]
[White "Short, Nigel D"]
[Black "Timman, Jan H"]
[Result "1-0"]

1.e4 Nf6 2.e5 Nd5 3.d4 d6 4.Nf3 g6 5.Bc4 Nb6 6.Bb3 Bg7 7.Qe2 Nc6 8.O-O O-O 9.h3 a5 10.a4 dxe5 11.dxe5 Nd4
12.Nxd4 Qxd4 13.Re1 e6 14.Nd2 Nd5 15.Nf3 Qc5 16.Qe4 Qb4 17.Bc4 Nb6 18.b3 Nxc4 19.bxc4 Re8 20.Rd1 Qc5 21.Qh4 b6
22.Be3 Qc6 23.Bh6 Bh8 24.Rd8 Bb7 25.Rad1 Bg7 26.R8d7 Rf8 27.Bxg7 Kxg7 28.R1d4 Rae8 29.Qf6+ Kg8 30.h4 h5 31.Kh2
Rc8 32.Kg3 Rce8 33.Kf4 Bc8 34.Kg5 1-0
"""
POS_FEN = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPPKPPP/RNBQ1BNR b kq - 1 2"
S, P, POS = "search_master_games", "get_game_pgn", "find_games_by_position"


def _final(pgn):
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    return board.fen()


def _loaded(pgn=KT, results=(), earlier=()):
    ctx = CheckContext.from_fens([None, _final(pgn), _final(pgn)], [pgn], question="")
    ctx.db_tracked = True
    ctx.db_results = list(results)
    ctx.db_results_earlier = list(earlier)
    acd.note_board_game(ctx, pgn)
    return ctx


def _plain(results=(), earlier=(), fen=chess.STARTING_FEN, language="ru"):
    ctx = CheckContext.from_fens([fen], question="")
    ctx.db_tracked = True
    ctx.language = language
    ctx.db_results = list(results)
    ctx.db_results_earlier = list(earlier)
    return ctx


# ── the loaded game: theory, the student's games, other players' games ─────────────────────────────────────────

THEORY_BESIDE_KT = [
    "Против Пирца белые часто играют австрийскую атаку: 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.f4.",
    "Система 1.e4 d6 2.d4 Nf6 3.f3 тоже встречается против Пирца.",
    "Классическая система против Пирца — 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3 Bg7 5.Be2 O-O 6.O-O c6.",
    "Через 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3 Bg7 5.Qd2 Ng4 чёрные сразу трогают слона.",
    "Against the Pirc, White often plays the Austrian Attack: 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.f4 Bg7 5.Nf3.",
]
OTHER_GAMES_BESIDE_KT = [
    "В партии против petr77 на 12-м ходу белые взяли пешку на e5.",
    "В партии с petr77 после 1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 белые сыграли 4.c3.",
    "В партии Иванов – Петров, которую ты прислал, на 9-м ходу белые сыграли 9.Nd5.",
    "В той партии, что ты играл вчера, на 15-м ходу чёрные взяли ферзя на d1.",
    "В твоей партии против petr77 белые на 5-м ходу сыграли 5.d4.",
    "In the game against bob_99, White castled queenside on move 9.",
]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", THEORY_BESIDE_KT + OTHER_GAMES_BESIDE_KT)
def test_theory_and_other_games_are_not_the_loaded_game(sentence):
    ctx = _loaded()
    assert acd.loaded_game_issues(sentence, ctx) == []
    assert check_sentence(sentence, _loaded()) == []


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "В партии Каспаров – Топалов дебют шёл 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.f4.",
    "Начало этой партии — 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Nf3.",
    "Дебют партии — 1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3 c6.",
])
def test_the_same_line_told_as_the_game_is_still_judged(sentence):
    assert acd.loaded_game_issues(sentence, _loaded())


TOLD_RIGHT = [
    (KT, "На 24-м ходу белые взяли пешку на d4 ладьёй."),
    (KT, "На 14-м ходу чёрные взяли пешку d4 пешкой."),
    (KT, "Каспаров рокировал в длинную сторону на 11-м ходу."),
    (KT, "На 30-м ходу белые взяли слона на b7 ладьёй, а Топалов в ответ пошёл ферзём на c4."),
    (KT, "Чёрный король в этой партии прошёл с c8 на d1."),
    (ST, "На 29-м ходу белые поставили ферзя на f6 с шахом."),
    (ST, "На 23-м ходу Тимман отвёл слона на h8."),
    (ST, "В партии на 24-м ходу ладья белых вторглась на d8."),
    (ST, "В партии Шорт – Тимман король белых прошёл с g1 на g5."),
    (ST, "Партия 34.Kg5 жүрісінен кейін аяқталды."),
]
TOLD_WRONG = [
    (KT, "Топалов на 14-м ходу взял пешку на d4 конём."),
    (KT, "Каспаров рокировал в короткую сторону на 11-м ходу."),
    (KT, "В партии чёрные на 13-м ходу рокировали коротко: 13...O-O."),
    (KT, "На 30-м ходу белые взяли слона на b7 ладьёй, а Топалов в ответ пошёл ферзём на d5."),
    (ST, "Белые поставили ферзя на f7 с шахом на 29-м ходу."),
    (ST, "На 33-м ходу чёрные отвели слона на a6."),
    (ST, "В партии на 24-м ходу ладья белых вторглась на d7."),
    (ST, "В партии Шорт – Тимман король белых прошёл с g1 на h6."),
    (ST, "Партия 33.Kg5 жүрісінен кейін аяқталды."),
    (ST, "Ақтар 27.Bg5 жүрісімен пілді шегерді."),
]


@pytest.mark.unit
@pytest.mark.parametrize("pgn,sentence", TOLD_RIGHT)
def test_the_game_told_right_in_words_passes(pgn, sentence):
    assert check_sentence(sentence, _loaded(pgn)) == []


@pytest.mark.unit
@pytest.mark.parametrize("pgn,sentence", TOLD_WRONG)
def test_the_game_told_wrong_in_words_is_caught(pgn, sentence):
    assert acd.loaded_game_issues(sentence, _loaded(pgn))


@pytest.mark.unit
def test_the_reply_is_judged_against_the_next_ply():
    issues = acd.loaded_game_issues("На 30-м ходу белые взяли слона на b7 ладьёй, а Топалов в ответ съел ферзя на d5.",
                                    _loaded())
    assert issues and "30...Qc4" in issues[0]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Скандинавская защита начинается так: 1.e4 d5 2.exd5 Qxd5 3.Nc3 Qa5.",  # «not possible at move 2 of the game»
])
def test_a_line_of_another_opening_is_not_judged_at_move_n_of_the_game(sentence):
    assert check_sentence(sentence, _loaded()) == []


@pytest.mark.unit
def test_the_past_tense_about_the_loaded_game_is_any_moment_of_it():
    bf = """[White "Byrne, Donald"]
[Black "Fischer, Robert James"]
[Date "1956.10.17"]
[Result "0-1"]

1.Nf3 Nf6 2.c4 g6 3.Nc3 Bg7 4.d4 O-O 5.Bf4 d5 6.Qb3 dxc4 7.Qxc4 c6 8.e4 Nbd7 9.Rd1 Nb6 10.Qc5 Bg4 11.Bg5 Na4
12.Qa3 Nxc3 13.bxc3 Nxe4 14.Bxe7 Qb6 15.Bc4 Nxc3 16.Bc5 Rfe8+ 17.Kf1 Be6 18.Bxb6 Bxc4+ 19.Kg1 Ne2+ 20.Kf1 Nxd4+
21.Kg1 Ne2+ 22.Kf1 Nc3+ 23.Kg1 axb6 24.Qb4 Ra4 25.Qxb6 Nxd1 26.h3 Rxa2 27.Kh2 Nxf2 28.Re1 Rxe1 29.Qd8+ Bf8
30.Nxe1 Bd5 31.Nf3 Ne4 32.Qb8 b5 33.h4 h5 34.Ne5 Kg7 35.Kg1 Bc5+ 36.Kf1 Ng3+ 37.Ke1 Bb4+ 38.Kd1 Bb3+ 39.Kc1 Ne2+
40.Kb1 Nc3+ 41.Kc1 Rc2# 0-1
"""
    assert check_sentence("Ферзь на b6 был под боем, и Фишер сознательно его оставил.", _loaded(bf)) == []


# ── claims about the database ───────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "В базе таких партий нет.",
    "Мастера в этой расстановке не играли — база не вернула ни одной партии.",
    "Таких партий у мастеров в базе не нашлось.",
    "В базе мастеров нет ни одной партии, где белые так рано пошли королём.",
])
def test_an_empty_position_search_answers_a_claim_that_names_no_game(sentence):
    assert acd.db_claim_issues(sentence.lower(), _plain([(POS, "empty")], fen=POS_FEN), sentence) == []


@pytest.mark.unit
def test_an_empty_position_search_says_nothing_of_a_named_game():
    s = "Партии Каспарова с Топаловым в базе нет."
    assert acd.db_claim_issues(s.lower(), _plain([(POS, "empty")], fen=POS_FEN), s)


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Как я уже говорил, этой партии в базе нет.",
    "Ту партию база не нашла, так что предлагаю разобрать похожую позицию.",
    "Той партии в базе нет, я проверял.",
    "Повторю: в базе такой партии не нашлось.",
    "Мы уже убедились, что в базе этой партии нет, так что давай разберём похожую.",
])
def test_said_of_an_earlier_empty_search(sentence):
    assert acd.db_claim_issues(sentence.lower(), _plain(earlier=[(S, "empty")]), sentence) == []
    # …but not when the earlier searches found the game
    assert acd.db_claim_issues(sentence.lower(), _plain(earlier=[(S, "found"), (P, "found")]), sentence)


@pytest.mark.unit
@pytest.mark.parametrize("sentence,language", [
    ("I don't have access to the games database.", "en"),
    ("Я поискал в базе, но ничего не нашёл.", "ru"),
    ("Я проверил базу — этой партии там нет.", "ru"),
    ("Менің партиялар базасына қолым жетпейді.", "kk"),
])
def test_database_claims_with_no_search_are_caught(sentence, language):
    assert acd.db_claim_issues(sentence.lower(), _plain(language=language), sentence)


@pytest.mark.unit
def test_ill_is_no_player_name():
    ctx = _plain([(S, "found"), (P, "found")], language="en")
    ctx.db_found_games = [{"white_name": "Kasparov, Garry", "black_name": "Topalov, Veselin", "date": "1999.01.20"}]
    s = "The database returned nothing, so I'll tell the game from memory."
    assert acd.db_claim_issues(s.lower(), ctx, s)


@pytest.mark.unit
def test_a_search_reported_then_its_empty_outcome_passes_after_an_empty_search():
    s = "Я поискал в базе, но ничего не нашёл."
    assert acd.db_claim_issues(s.lower(), _plain([(S, "empty")]), s) == []


# ── the answer check beside the move it warns against ───────────────────────────────────────────────────────────

BLACKBURNE = "r1b1kbnr/pppp1ppp/8/4N1q1/2BnP3/8/PPPP1PPP/RNBQK2R w KQkq - 1 5"


@pytest.mark.unit
def test_a_lure_is_not_advice():
    ctx = CheckContext.from_fens([None, BLACKBURNE, BLACKBURNE], [], question="что тут делать")
    s = "Соблазнительно сыграть Nxf7 — так все и попадаются: 5.Nxf7 Qxg2 6.Rf1 Qxe4+ 7.Be2 Nf3# — мат."
    assert proposed_move(s, ctx) is None
    assert proposed_move("Сыграй Bxf7+, это сильнее.", ctx) is not None


@pytest.mark.unit
def test_the_side_after_a_move_is_the_subject_of_its_attack():
    ctx = CheckContext.from_fens([None, BLACKBURNE, BLACKBURNE], [], question="что тут делать")
    s = "А вот брать конём на f7 нельзя — это как раз приманка: после Nxf7 чёрные бьют на g2, и дальше мат."
    assert check_sentence(s, ctx) == []


# ── «третью из списка» ──────────────────────────────────────────────────────────────────────────────────────────

MIAMI = [
    {"id": 3622938, "white_name": "Nakamura,Hikaru", "black_name": "Carlsen,Magnus", "date": "2026.10.18"},
    {"id": 3622935, "white_name": "Carlsen,Magnus", "black_name": "Sindarov,Javokhir", "date": "2026.10.18"},
    {"id": 3622932, "white_name": "Martínez Alcántara,José Eduardo", "black_name": "Sevian,Samuel", "date": "2026.10.17"},
    {"id": 3622931, "white_name": "Sindarov,Javokhir", "black_name": "Nakamura,Hikaru", "date": "2026.10.17"},
    {"id": 3622929, "white_name": "Sindarov,Javokhir", "black_name": "Caruana,Fabiano", "date": "2026.10.17"},
]
LISTED = """В базе 5 партий:

- 18.10: Накамура — Карлсен, ничья
- 18.10: Карлсен — Синдаров, 1-0
- 17.10: Мартинес Алькантара — Севиян, ничья
- 17.10: Синдаров — Накамура, 1-0
- 17.10: Синдаров — Каруана, 0-1

Какую загрузить?"""


@pytest.mark.unit
@pytest.mark.parametrize("message,ref", [
    ("загрузи третью из списка", ("n", 3)), ("а следующую?", ("next",)), ("открой №4", ("n", 4)),
    ("load the second one", ("n", 2)), ("последнюю из списка", ("last",)),
    ("последняя партия Накамуры — загрузи её", None), ("давай следующий ход", None), ("покажи 3 партии Карлсена", None),
    ("Дай мне задачку на вилку конём", None),
])
def test_a_message_that_points_into_the_list(message, ref):
    assert list_reference(message) == ref


@pytest.mark.unit
def test_the_list_numbered_as_the_answer_showed_it():
    assert shown_order(LISTED, MIAMI) == [g["id"] for g in MIAMI]
    reordered = "\n".join(["1) Синдаров — Каруана", "2) Мартинес Алькантара — Севиян", "3) Накамура — Карлсен",
                           "4) Карлсен — Синдаров", "5) Синдаров — Накамура"])
    assert shown_order(reordered, MIAMI) == [3622929, 3622932, 3622938, 3622935, 3622931]
    assert "get_game_pgn(game_id=3622932" in list_note("загрузи третью из списка", MIAMI, None, LISTED)
    assert "get_game_pgn(game_id=3622929" in list_note("а следующую?", MIAMI, 3622931, LISTED)
    assert "not in this list" in list_note("загрузи седьмую", MIAMI, None, LISTED)
    assert list_note("Что такое вилка?", MIAMI, None, LISTED) == ""


@pytest.mark.unit
def test_the_session_keeps_the_last_list_and_the_game_loaded():
    s = Session(user_id="games-db-check")
    s.add_message("user", "что есть с Майами?")
    s.note_db_tool(S, {}, json.dumps(MIAMI))
    s.note_db_tool(P, {"game_id": 3622932}, json.dumps({"id": 3622932, "pgn": "1.e4 *"}))
    s.add_message("assistant", LISTED)
    s.add_message("user", "а следующую?")
    games, loaded = s.recent_db_list()
    assert [g["id"] for g in games] == [g["id"] for g in MIAMI] and loaded == 3622932
    s.note_db_tool(S, {}, json.dumps(MIAMI[:1]))  # a search of one game keeps the list
    assert len(s.recent_db_list()[0]) == 5


# ── «задачку на вилку конём» ────────────────────────────────────────────────────────────────────────────────────

QUEEN_FORK = {"puzzle_id": "0CCGQ", "fen": "rn2k2r/pQ3ppp/5q2/2b5/8/2p3P1/P4P1P/R1B1K1NR w KQkq - 0 13",
              "solution": ["Qc8+", "Qd8", "Qxc5"], "themes": ["fork"], "rating": 1500}
KNIGHT_FORK = {"puzzle_id": "kf1", "fen": "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", "solution": ["Nc7+"],
               "themes": ["fork"], "rating": 900}


@pytest.mark.unit
def test_a_fork_by_the_knight_is_a_knight_fork():
    from src.tools.puzzles import made_by

    assert made_by(QUEEN_FORK, "fork", chess.QUEEN) and not made_by(QUEEN_FORK, "fork", chess.KNIGHT)


@pytest.mark.unit
def test_get_puzzle_passes_over_forks_by_other_pieces():
    from src import config
    from src.tools import puzzles

    calls = []

    def _find(**kw):
        calls.append(kw)
        return [dict(QUEEN_FORK)] if len(calls) == 1 else [dict(QUEEN_FORK, puzzle_id="q2"), dict(KNIGHT_FORK)]

    with patch.object(puzzles, "db_available", return_value=True), patch.object(puzzles, "find_puzzles", side_effect=_find), \
            patch.object(config, "COACH_PUZZLES_FROM_SITE", False):
        got = puzzles.get_puzzle(theme="fork", piece=chess.KNIGHT)
        assert got["on_board"] == "kf1"
        calls.clear()
        with patch.object(puzzles, "find_puzzles", return_value=[dict(QUEEN_FORK)]):
            got = puzzles.get_puzzle(theme="fork", piece=chess.KNIGHT)
        assert got["on_board"] == "0CCGQ" and "made by another piece" in got["how_to_show"]


# ── the text turn: the list's game by its id ────────────────────────────────────────────────────────────────────

USER = {"X-User-Id": "games-db-check"}
START = chess.STARTING_FEN
FIX = "Материал равный, у каждой стороны по ферзю."


def _agent(script, seen):
    import time
    from unittest.mock import MagicMock

    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0

    def _chat(message, stream_callback=None):
        seen.append(message)
        text = []
        for i, step in enumerate(script):
            if isinstance(step, tuple):
                tool, args, result = step
                agent.tool_start_callback(f"c{i}", tool, args)
                time.sleep(0.03)
                agent.tool_complete_callback(f"c{i}", tool, args, json.dumps(result))
            else:
                stream_callback(step)
                text.append(step)
            time.sleep(0.03)
        return "".join(text)

    agent.chat.side_effect = _chat
    return agent


@pytest.mark.unit
class TestTurn:
    @pytest.fixture(autouse=True)
    def _turn(self, monkeypatch):
        from fastapi.testclient import TestClient

        from src import config
        from src.middleware.rate_limiter import rate_limiter
        from src.sessions import session_store

        session_store._sessions.clear()
        rate_limiter.reset()
        for name, value in (("COACH_TWO_STAGE", False), ("COACH_ENGINE_NOTE", False), ("COACH_OPENING_PRESTEP", False),
                            ("COACH_SITE_PUZZLE_LOOKUP", False), ("COACH_ANSWER_CHECK", True),
                            ("COACH_ANSWER_FIX", True), ("COACH_RELATION_CHECK", "off")):
            monkeypatch.setattr(config, name, value)
        self.config = config
        self.monkeypatch = monkeypatch
        self.client = TestClient(__import__("src.server", fromlist=["app"]).app)
        self.seen = []
        yield
        session_store._sessions.clear()
        rate_limiter.reset()

    def _turn_with(self, script, message="Что тут делать белым?", session_id=None):
        from src.quick_reply import QuickReply
        from src.user_profile import UserProfile

        def _fix(**kw):
            kw["on_delta"](FIX)
            return QuickReply(model=kw["model"])

        body = {"message": message, "fen": START}
        if session_id:
            body["session_id"] = session_id
        with patch("src.server._create_agent", side_effect=lambda **kw: _agent(script, self.seen)), \
                patch("src.server.load_user_profile", return_value=UserProfile(user_id="games-db-check")), \
                patch("src.quick_reply.stream_completion", side_effect=_fix), \
                patch("src.server.engine_note", return_value=None), \
                patch("src.server.log_event"):
            resp = self.client.post("/api/coach/chat", headers=USER, json=body)
        assert resp.status_code == 200
        return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]

    def test_the_third_of_the_list_is_named_to_the_model_by_its_id(self):
        frames = self._turn_with([(S, {"event": "Miami"}, MIAMI), LISTED], message="Что есть в базе с Майами?")
        sid = next(f["session_id"] for f in frames if f.get("session_id"))
        self._turn_with(["Загружаю."], message="загрузи третью из списка", session_id=sid)
        assert "get_game_pgn(game_id=3622932" in self.seen[-1]
        assert "get_game_pgn(game_id=" not in self.seen[0]


@pytest.mark.unit
def test_the_other_side_after_a_comma_is_the_reply_unless_a_later_move_is_said():
    assert acd.loaded_game_issues("В партии на 30-м ходу белые взяли слона на b7 ладьёй, а чёрные бьют пешку на f2 ферзём.",
                                  _loaded())
    assert acd.loaded_game_issues("На 30-м ходу белые взяли слона на b7 ладьёй, а чёрные ответили ферзём на c4.",
                                  _loaded()) == []
    # a later move is not the reply — nor part of the first clause's claim
    assert acd.loaded_game_issues("На 30-м ходу белые взяли слона на b7 ладьёй, а чёрные потом забрали ферзя на f6.",
                                  _loaded()) == []


@pytest.mark.unit
def test_a_line_from_the_middle_of_the_opening_is_theory_only_when_the_sentence_says_so():
    berlin = ('[White "Nakamura,Hikaru"]\n[Black "Firouzja,Alireza"]\n[Date "2026.10.17"]\n[Result "1/2-1/2"]\n\n'
              "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Nxe4 5. d4 Nd6 6. Bxc6 dxc6 7. dxe5 Nf5 8. Qxd8+ Kxd8 1/2-1/2")
    assert acd.loaded_game_issues("После 5.d4 Nd6 6.Bxc6 dxc6 7.dxe5 Ne4 белые давят.", _loaded(berlin))
    assert acd.loaded_game_issues("В берлинской защите после 5.d4 Nd6 6.Bxc6 dxc6 7.dxe5 Ne4 белые давят.",
                                  _loaded(berlin)) == []


@pytest.mark.unit
def test_the_list_matched_in_the_models_own_spelling_and_order():
    games = MIAMI + [{"id": 3622927, "white_name": "Nakamura,Hikaru", "black_name": "Firouzja,Alireza"},
                     {"id": 3622902, "white_name": "Firouzja,Alireza", "black_name": "Sindarov,Javokhir"}]
    answer = ("Вот список:\n\n- Карлсен — Синдаров 1-0\n- Накамура — Карлсен ½-½\n- Синдаров — Накамура 1-0\n"
              "- Синдаров — Каруана 0-1\n- Накамура — Фируджа ½-½\n- Фируджа — Синдаров 0-1\n"
              "- Мартинес Альтамира — Севиян ½-½\n\nКакую загрузить?")
    assert shown_order(answer, games) == [3622935, 3622938, 3622931, 3622929, 3622927, 3622902, 3622932]
    assert "get_game_pgn(game_id=3622931" in list_note("загрузи третью из списка", games, None, answer)
    # items that cannot be told apart: no number of ours, the model counts in its own list
    vague = "- Синдаров — кто-то\n- Синдаров — кто-то ещё\n- и другие"
    note = list_note("загрузи вторую", games, None, vague)
    assert "YOUR previous answer" in note and "game_id=" not in note
