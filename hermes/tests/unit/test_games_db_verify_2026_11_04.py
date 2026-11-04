"""The verification of 04.11 on «any game from the database reaches the board» (src/answer_check_db.py,
src/server.py, src/tool_selector.py, src/sessions.py).

Found by class, without a model, on the stored production answers and 200 new true sentences:
  * the loaded game's moves judged every numbered move of a sentence while the game's id stayed on the board — an
    opening's moves, a puzzle, a what-if («На 20.Qc2 чёрные ответят…»), the student's game were cut (19 of 30); the
    game also stayed in the check after a tool put a puzzle up;
  * a tool call after a cut sentence called the rewrite off even when no text followed: an empty answer;
  * «нет доступа» / «не могу открыть … партию» was a database claim without the database named, and any «поиск /
    search / база» was the games database (the web, the engine, the tablebase, «в поисках контригры»);
  * an earlier turn's search and «этой партии нет, но есть другие» were judged against this turn's tools only;
  * the database game on the board carried the game tools on every turn with «с», «это» or a square's digit;
  * the tool selection was ten times slower (uncached word roots).
"""

import io
import json
import time
from unittest.mock import MagicMock, patch

import chess
import chess.pgn
import pytest

from src import answer_check_db as acd
from src import tool_selector as ts
from src.answer_check import CheckContext, check_sentence
from src.sessions import Session


@pytest.fixture(autouse=True)
def _db_checks_on(monkeypatch):
    """These tests judge what the database checks cut: both on (they ship in shadow — test_games_db_switches_2026_11_04)."""
    from src import config

    monkeypatch.setattr(config, "COACH_DB_CLAIM_CHECK", "on")
    monkeypatch.setattr(config, "COACH_LOADED_GAME_CHECK", "on")

S, P = "search_master_games", "get_game_pgn"

WCH6 = """[Event "FIDE World Championship 2021"]
[Site "Dubai UAE"]
[Date "2021.12.03"]
[Round "6"]
[White "Carlsen,Magnus"]
[Black "Nepomniachtchi,Ian"]
[Result "1-0"]

1. d4 Nf6 2. Nf3 d5 3. g3 e6 4. Bg2 Be7 5. O-O O-O 6. b3 c5 7. dxc5 Bxc5 8. c4
dxc4 9. Qc2 Qe7 10. Nbd2 Nc6 11. Nxc4 b5 12. Nce5 Nb4 13. Qb2 Bb7 14. a3 Nc6
15. Nd3 Bb6 16. Bg5 Rfd8 17. Bxf6 gxf6 18. Rac1 Nd4 19. Nxd4 Bxd4 20. Qa2 Bxg2
21. Kxg2 Qb7+ 22. Kg1 Qe4 23. Qc2 a5 24. Rfd1 Kg7 25. Rd2 Rac8 26. Qxc8 Rxc8
27. Rxc8 h5 28. h4 f5 29. Nc5 Qe5 30. e3 Bxe3 31. fxe3 Qxe3+ 32. Rf2 e5 33. b4
a4 34. Re8 Qxa3 35. Nd7 Qc1+ 36. Rf1 Qc3 37. Nxe5 Qxb4 38. Rxf5 Qd4+ 39. Kh2 f6
40. Re7+ Kf8 41. Rf7+ Ke8 42. Re7+ Kd8 43. Nc6+ Kc8 44. Nxd4 Kd8 45. Nc6+ Kc8
46. Rxb5 a3 47. Rb8# 1-0
"""


def _final(pgn):
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    return board.fen()


def _loaded_ctx(results=()):
    """The verification's context: the game's final position on the board, its id there (note_board_game)."""
    ctx = CheckContext.from_fens([_final(WCH6)], [WCH6], question="")
    ctx.db_tracked = True
    if results:
        ctx.db_results = list(results)
    acd.note_board_game(ctx, WCH6)
    return ctx


def _plain_ctx(results=(), earlier=None, found_games=None):
    ctx = CheckContext.from_fens([chess.STARTING_FEN], question="")
    ctx.db_tracked = True
    if results:
        ctx.db_results = list(results)
    if earlier is not None:
        ctx.db_results_earlier = list(earlier)
    if found_games is not None:
        ctx.db_found_games = list(found_games)
    return ctx


# ── the loaded game: only sentences that tell it ────────────────────────────────────────────────────────────────

OTHER_LINES = [
    "Итальянская партия начинается ходами 1.e4 e5 2.Nf3 Nc6 3.Bc4.",
    "В сицилианской защите после 1.e4 c5 белые чаще всего играют 2.Nf3.",
    "Защита Каро-Канн — это 1.e4 c6.",
    "В защите Каро-Канн чёрные отвечают 1...c6.",
    "Испанская партия: 1.e4 e5 2.Nf3 Nc6 3.Bb5.",
    "Ферзевый гамбит начинается с 1.d4 d5 2.c4.",
    "После 1.e4 e5 2.Nf3 Nc6 3.Bc4 Nd4 4.Nxe5 чёрные играют 4...Qg5 с вилкой.",
    "Детский мат: 1.e4 e5 2.Bc4 Nc6 3.Qh5 Nf6 4.Qxf7#.",
    "Мат Легаля: 1.e4 e5 2.Nf3 d6 3.Bc4 Bg4 4.Nc3 g6 5.Nxe5.",
    "На 20.Qc2 чёрные просто ответят 20...Bxg2.",
    "20.Qc2 здесь проигрывает пешку после 20...Bxg2 21.Kxg2 Qb7+.",
    "В твоей прошлой партии на 12-м ходу ты взял пешку на e5 конём.",
    "В королевском гамбите после 1.e4 e5 2.f4 белые жертвуют пешку.",
    "The Italian Game starts 1.e4 e5 2.Nf3 Nc6 3.Bc4.",
    "In the Sicilian, after 1.e4 c5 White usually plays 2.Nf3.",
    "Лондонская система: 1.d4 d5 2.Bf4.",
    "В голландской защите чёрные отвечают на 1.d4 ходом 1...f5.",
    "Защита Филидора: 1.e4 e5 2.Nf3 d6.",
    "Шотландская партия: 1.e4 e5 2.Nf3 Nc6 3.d4.",
    "Итальянская партия, о которой ты спрашивал раньше, начинается 1.e4 e5 2.Nf3 Nc6 3.Bc4.",
]
GAME_TOLD_RIGHT = [
    "17.Bxf6 gxf6 испортил чёрным пешечную структуру.",
    "На 26-м ходу белые взяли ладью на c8 ферзём.",
    "Партия закончилась матом: 47.Rb8#.",
    "20...Bxg2 21.Kxg2 Qb7+ — чёрные разменяли слонов.",
    "На 26-м ходу белые отдали ферзя за две ладьи: 26.Qxc8 Rxc8 27.Rxc8.",
]
GAME_TOLD_WRONG = [
    "В этой партии на 20-м ходу белые сыграли 20.Qc2.",  # «в этой партии»
    "Карлсен сыграл 20.Qc2, и чёрные разменяли слонов.",  # a side named
    "После 19.Nxd4 Bxd4 20.Qc2 белые держат равенство.",  # two plies of the game, then a move it did not have
    "В партии на 1.d4 чёрные ответили 1...d5.",
    "Непомнящий ответил 20...Bd5.",
]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", OTHER_LINES + GAME_TOLD_RIGHT)
def test_other_lines_and_right_moves_pass_beside_the_loaded_game(sentence):
    assert acd.loaded_game_issues(sentence, _loaded_ctx()) == []
    assert not [i for i in check_sentence(sentence, _loaded_ctx()) if "game on the board" in i]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", GAME_TOLD_WRONG)
def test_a_wrong_move_told_of_the_game_is_caught(sentence):
    assert acd.loaded_game_issues(sentence, _loaded_ctx())


@pytest.mark.unit
def test_a_line_written_from_the_game_then_leaving_it_without_a_number_is_judged_only_when_tied():
    ctx = _loaded_ctx()
    assert acd.loaded_game_issues("После 19.Nxd4 Bxd4 20.Qa2 Bd5 у чёрных инициатива.", ctx)  # 3 plies, then Bd5
    assert acd.loaded_game_issues("После 1.d4 d5 у чёрных крепкий центр.", ctx) == []  # one ply: another line


@pytest.mark.unit
def test_the_game_leaves_the_check_when_the_board_shows_something_else():
    ctx = _loaded_ctx()
    acd.forget_board_game(ctx)
    assert acd.loaded_game_issues("В этой партии на 20-м ходу белые сыграли 20.Qc2.", ctx) == []
    from src.server import _student_side_note

    assert "never «ты»" not in _student_side_note(ctx)


# ── claims about the database ───────────────────────────────────────────────────────────────────────────────────

NOT_DATABASE_CLAIMS = [
    "Точный рейтинг назвать не могу — у меня нет доступа к актуальному рейтинг-листу, а мои данные заканчиваются раньше.",
    "Не могу загрузить партию по этой ссылке: lichess отвечает, что она закрыта.",
    "Не могу открыть эту партию — ссылка ведёт на удалённую игру.",
    "Не получится загрузить эту игру с chess.com, пока профиль закрыт.",
    "У меня нет доступа к твоему аккаунту на chess.com — пришли ссылку на партию.",
    "У меня нет доступа к твоим партиям на lichess без ссылки.",
    "Не могу показать твою партию, пока ты её не импортируешь.",
    "I can't load that game from chess.com: the link is private.",
    "I have no access to your lichess account, so send me a link to the game.",
    "У меня нет доступа к трансляции этого турнира.",
    "Нет доступа к живым данным FIDE, поэтому называю рейтинг на 1 октября.",
    "Нет доступа к микрофону — разреши его в настройках браузера.",
    "Я поискал в интернете, но ничего не нашёл о результатах этого турнира.",
    "Поиск в интернете ничего не дал по этому турниру.",
    "My web search found nothing about that event.",
    "Движок в своём поиске не нашёл ничего лучше, чем Nf3.",
    "The engine's search didn't find anything better than Nf3.",
    "Таблицы эндшпиля (база Налимова) не содержат позиций с восемью фигурами.",
    "Эндшпильная база Syzygy не хранит позиций больше чем с семью фигурами.",
    "В поисках контригры чёрные не нашли ничего лучше, чем размен ферзей.",
    "Поиск защиты ничего не дал: мат неизбежен.",
    "Поиск задачи по теме «вилка» ничего не нашёл для рейтинга 800.",
    "Не могу показать эту партию на доске, пока не найду её в базе — дай секунду.",
    "Партия Ананд — Карлсен не хранится у меня в памяти целиком, но её можно найти в базе.",
]
STILL_CLAIMS = [
    "Не получилось — я не вижу твоей прошлой партии Карлсена из базы: у меня в этом сеансе нет ссылки на неё, "
    "а поиск по базе мне сейчас ничего не вернул.",
    "Проверил, база в этот раз не отдала партию — попробуем ещё раз чуть позже или возьмём другую из списка.",
    "Честно скажу: партию Карлсен — Гукеш из базы сейчас достать не вышло — поиск по базе ничего не вернул, а свежих "
    "новостей у меня нет.",
    "Не могу загрузить конкретную партию Абдусатторова против Синдарова — у меня нет доступа к базе партий, я работаю "
    "с той позицией, что стоит на доске.",
    "Разыграть партию по ходам я не могу — в базе у меня лежат только данные о встречах, а не сами ходы.",
    "I couldn't find that game in the database.",
]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", NOT_DATABASE_CLAIMS)
def test_other_sources_and_other_bases_are_no_database_claims(sentence):
    assert acd.db_claim_issues(sentence.lower(), _plain_ctx(), sentence) == []


@pytest.mark.unit
@pytest.mark.parametrize("sentence", STILL_CLAIMS)
def test_database_claims_without_its_tool_are_still_caught(sentence):
    assert acd.db_claim_issues(sentence.lower(), _plain_ctx(), sentence) == [acd.DB_NOT_RUN_ISSUE]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Как я уже говорил, поиск по базе в прошлый раз ничего не нашёл по Талю 1952 года.",
    "В прошлый раз база не нашла эту партию, потому что TWIC начинается с 1994 года.",
    "Last time the database search found nothing because the name was misspelled.",
])
def test_an_earlier_search_is_judged_by_what_the_database_said_then(sentence):
    assert acd.db_claim_issues(sentence.lower(), _plain_ctx(), sentence) == []  # nothing known of it
    assert acd.db_claim_issues(sentence.lower(), _plain_ctx(earlier=[(S, "empty")]), sentence) == []
    assert acd.db_claim_issues(sentence.lower(), _plain_ctx(earlier=[(S, "found"), (P, "found")]), sentence) == \
        [acd.DB_EARLIER_FOUND_ISSUE]


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Именно этой партии в базе нет, но есть три других их партии.",
    "That exact game isn't in the database, but I found two other games of theirs.",
    "Партии из Ташкента в базе нет, зато есть их встреча в Майами.",
])
def test_a_search_that_found_other_games_lets_the_missing_one_be_said(sentence):
    assert acd.db_claim_issues(sentence.lower(), _plain_ctx([(S, "found")]), sentence) == []


@pytest.mark.unit
def test_a_missing_year_or_player_against_what_the_search_returned():
    games = [{"white_name": "Carlsen,Magnus", "black_name": "Gukesh,D", "date": "2026.01.20"}]
    ctx = _plain_ctx([(S, "found")], found_games=games)
    year = "Такой партии 2019 года в базе нет."
    assert acd.db_claim_issues(year.lower(), ctx, year) == []
    assert acd.db_claim_issues("Такой партии в базе нет.", ctx, "Такой партии в базе нет.") == [acd.DB_FOUND_ISSUE]
    other = "Такой партии с Каруаной в базе нет."
    assert acd.db_claim_issues(other.lower(), ctx, other) == []
    same = "Такой партии с Гукешем в базе нет."
    assert acd.db_claim_issues(same.lower(), ctx, same) == [acd.DB_FOUND_ISSUE]


@pytest.mark.unit
def test_search_results_record_the_games_returned():
    ctx = _plain_ctx()
    acd.note_tool_result(ctx, S, json.dumps([{"id": 1, "white_name": "Sindarov,J", "black_name": "Nakamura,H",
                                               "date": "2026.03.10"}]))
    assert ctx.db_results == [(S, "found")] and ctx.db_found_games[0]["id"] == 1


@pytest.mark.unit
def test_session_keeps_the_database_results_of_earlier_turns():
    session = Session(id="s", user_id="u")
    session.add_message("user", "Найди партию Таля 1952")
    session.note_db_result(S, "empty")
    assert session.earlier_db_results() == []  # this turn's own
    session.add_message("assistant", "Не нашёл.")
    session.add_message("user", "а почему?")
    assert session.earlier_db_results() == [(S, "empty")]


# ── the game tools carried by the board's game ─────────────────────────────────────────────────────────────────

ORDINARY_WITH_THE_GAME_ON_THE_BOARD = [
    "Что если d5?", "Почему не Nf3 с угрозой?", "Это хороший ход?", "Что такое вилка?", "Объясни план после 15 хода",
    "А что если пойти пешкой на 4-ю горизонталь?", "покажи эту позицию", "а другой план?", "С чего начать атаку?",
    "Какой план у чёрных в этой позиции?", "Что такое английское начало?", "Дай задачу на вилку",
    "Открой урок про связку", "Как играть против сицилианской защиты?",
]


@pytest.mark.unit
@pytest.mark.parametrize("query", ORDINARY_WITH_THE_GAME_ON_THE_BOARD)
def test_ordinary_questions_do_not_carry_the_game_tools(query):
    assert ts.game_context_tools(query, (), None, {"twic_game_id": 3622931}) == ()


@pytest.mark.unit
@pytest.mark.parametrize("query", ["Что такое английское начало?", "Дай задачу на вилку", "Открой урок про связку"])
def test_another_object_drops_the_trail_too(query):
    assert ts.game_context_tools(query, (), game_tools_turns_ago=1) == ()
    assert ts.game_context_tools(query, ("Найди партию Синдаров — Накамура",)) == ()


@pytest.mark.unit
@pytest.mark.parametrize("query", ["а 2-ю?", "загрузи 3-ю партию", "покажи ещё одну", "а против Гукеша?", "а третью?",
                                   "покажи последнюю", "and the next one?"])
def test_real_follow_ups_carry_them_with_the_game_on_the_board(query):
    assert ts.game_context_tools(query, (), None, {"twic_game_id": 3622931}) == ts.GAME_TOOLS


@pytest.mark.unit
def test_word_roots_are_cached():
    assert hasattr(ts._root, "cache_info") and hasattr(ts._word_matches, "cache_info")
    ts._root.cache_clear()
    ts._root("базе")
    ts._root("базе")
    assert ts._root.cache_info().hits >= 1


# ── the text turn: the rewrite held across a tool call ──────────────────────────────────────────────────────────

ST = chess.STARTING_FEN
USER = {"X-User-Id": "games-db-verify"}
CUT = "У белых лишний ферзь. "
OK = "Позиция примерно равная. "
FIX = "Материал равный, у каждой стороны по ферзю."
ARROWS = ("board_control", {"action": "draw_arrows"}, {"ok": True})
TOOL = ("analyze_position", {"fen": ST}, {"evaluation": 0.3, "best_move": "e4"})


def _agent(script):
    agent = MagicMock()
    agent.tools = []
    agent.model = "deepseek/deepseek-v4.1-flash"
    agent._api_call_count = 1
    agent.max_iterations = 5
    agent.session_prompt_tokens = agent.session_completion_tokens = agent.session_cache_read_tokens = 0

    def _chat(message, stream_callback=None):
        text = []
        for i, step in enumerate(script):
            if isinstance(step, tuple):
                tool, args, result = step
                agent.tool_start_callback(f"c{i}", tool, args)
                time.sleep(0.05)
                agent.tool_complete_callback(f"c{i}", tool, args, json.dumps(result))
            else:
                stream_callback(step)
                text.append(step)
            time.sleep(0.05)
        return "".join(text)

    agent.chat.side_effect = _chat
    return agent


@pytest.mark.unit
class TestHeldRewrite:
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
        self.client = TestClient(__import__("src.server", fromlist=["app"]).app)
        self.fix_prompts = []
        yield
        session_store._sessions.clear()
        rate_limiter.reset()

    def _turn_with(self, script, message="Что тут делать белым?", delay=0.6, fix_text=FIX):
        from src.quick_reply import QuickReply
        from src.user_profile import UserProfile

        def _fix(**kw):
            self.fix_prompts.append(kw["messages"][1]["content"])
            deadline = time.monotonic() + delay
            while time.monotonic() < deadline:
                if kw["should_abort"]():
                    return QuickReply(model=kw["model"])
                time.sleep(0.01)
            kw["on_delta"](fix_text)
            return QuickReply(model=kw["model"])

        with patch("src.server._create_agent", side_effect=lambda **kw: _agent(script)), \
                patch("src.server.load_user_profile", return_value=UserProfile(user_id="games-db-verify")), \
                patch("src.quick_reply.stream_completion", side_effect=_fix), \
                patch("src.server.engine_note", return_value=None), \
                patch("src.server.log_event"):
            resp = self.client.post("/api/coach/chat", headers=USER, json={"message": message, "fen": ST})
        assert resp.status_code == 200
        frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
        return "".join(f.get("delta", "") for f in frames), frames

    # The held rewrite is played like any rewrite: through src/rewrite_proof (next-1031, fix1102 K6), which keeps it only
    # when its board words are proven. These two test the hold, so the rewrite is taken as proven here (as next-1031 did
    # for main's earlier rewrite tests); the last one is the same turn under the real proof (integration 04.11).
    def test_a_draft_that_ends_at_the_tool_gets_the_rewrite(self, monkeypatch):
        from src.rewrite_proof import Proof

        monkeypatch.setattr("src.rewrite_proof._prove", lambda sentence, ctx: Proof("proven"))
        shown, frames = self._turn_with([CUT, ARROWS])
        assert shown == FIX  # was '' (an empty answer)
        assert any("tool_call" in f for f in frames)

    def test_text_before_the_cut_and_a_tool_after_it_keep_the_rewrite(self, monkeypatch):
        from src.rewrite_proof import Proof

        monkeypatch.setattr("src.rewrite_proof._prove", lambda sentence, ctx: Proof("proven"))
        shown, _ = self._turn_with([OK, CUT, ARROWS])
        assert shown == OK + FIX  # was only «Позиция примерно равная.»

    def test_an_unproven_held_rewrite_is_dropped_and_the_answer_is_never_empty(self):
        # «Материал равный…» — nothing this turn proves it (no engine line, the relation check off): the rewrite is
        # abandoned like any unproven one, and with no draft left the student gets the plain line, not ''
        shown, _ = self._turn_with([CUT, ARROWS])
        assert FIX not in shown and "лишний ферзь" not in shown and "провер" in shown
        shown, _ = self._turn_with([OK, CUT, ARROWS])
        assert shown == OK

    def test_the_draft_after_the_tool_still_stands_in_for_the_rewrite(self):
        after = "После проверки: план тот же, развивай фигуры. "
        shown, _ = self._turn_with([OK, CUT, TOOL, after])
        assert shown == OK + after
        assert "лишний ферзь" not in shown

    def test_a_database_tool_after_the_cut_writes_the_rewrite_again_with_its_results(self):
        found = [{"id": 3622931, "white_name": "Sindarov,Javokhir", "black_name": "Nakamura,Hikaru",
                  "date": "2026.03.10"}]
        shown, _ = self._turn_with(["Поиск по базе ничего не вернул. ", (S, {"player": "Синдаров"}, found)],
                                   message="Найди партию Синдаров — Накамура", fix_text="Нашёл партию Синдаров — Накамура.")
        assert shown == "Нашёл партию Синдаров — Накамура."
        assert len(self.fix_prompts) == 2
        assert "search_master_games — found" in self.fix_prompts[1]
        assert "search_master_games — found" not in self.fix_prompts[0]

    def test_a_puzzle_put_up_after_the_game_takes_the_game_out_of_the_check(self):
        from src.tools import twic_search

        game = {"id": 3622931, "pgn": WCH6, "headers": {"White": "Carlsen,Magnus", "Black": "Nepomniachtchi,Ian"},
                "moves": twic_search.move_list(WCH6),
                "board_actions": [{"type": "load_pgn", "pgn": WCH6, "game_id": 3622931}]}
        puzzle = {"type": "set_fen", "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"}
        told = "В этой партии на 20-м ходу белые сыграли 20.Qc2. "
        shown, _ = self._turn_with([(P, {"game_id": 3622931, "show": True}, game), ("board_control", {}, puzzle),
                                    "Вот задача. ", told], fix_text="")
        assert told.strip() in shown
        shown, _ = self._turn_with([(P, {"game_id": 3622931, "show": True}, game), "Партия на доске. ", told],
                                   fix_text="")
        assert "20.Qc2" not in shown  # with the game still on the board the wrong move is cut
