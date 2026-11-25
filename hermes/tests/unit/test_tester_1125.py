"""Tester's report of 25.11 (the eighth): the coach's side of it.

1–2  a comment on a move told what the move did not do («напал на ферзя», «сохранил преимущество»);
4    the game finished before a rematch was not there to ask about;
6    sessions named by a service text, a button's request, a pasted position;
7    «следующий урок» was the lesson opened last, not the next one of the Learn page;
8    a rule's example refused because the site's lesson on it is locked; the warm-up's break said a turn late.
"""

from types import SimpleNamespace as NS

import chess
import chess.pgn
import pytest

from src import game_mode, prior_game, rule_examples, session_label, warmup
from src.answer_check import CheckContext, SentenceGate
from src.tools import learning_path as lp

pytestmark = pytest.mark.unit

GAME_1 = "e4 e5 d4 exd4 Qxd4 Nc6 Qd3 Nd4 Qxd4 Nf6 Bd2".split()


def _state(moves, color, annotations):
    return {"student_color": color, "engine_elo": 1200, "moves": list(moves), "annotations": annotations,
            "status": "playing"}


def _gate(moves, color, engine_eval=None, record=True):
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    student = chess.WHITE if color == "white" else chess.BLACK
    ctx = CheckContext.from_fens([board.fen()], [str(chess.pgn.Game.from_board(board))], student_color=student)
    ctx.language = "ru"
    ctx.relation_surface = "game"
    ctx.comment_now = CheckContext.from_fens([board.fen()], [], student_color=student)
    ctx.comment_now.language = "ru"
    if record:
        ctx.game_moves = list(moves)
    ctx.engine_eval = engine_eval
    return SentenceGate(ctx, enabled=True)


def _issues(gate, text):
    return [i for _, issues, _ in gate.feed(text) + gate.flush() for i in issues]


# ── 1–2: the comment on a move ────────────────────────────────────────────────────────────────────────────────────
def test_the_comment_is_told_what_the_move_attacks_and_what_it_does_not():
    state = _state(GAME_1, "black", [{"ply": 10, "san": "Nf6", "verdict": "ok", "cp_loss": 10, "eval_after": -450}])
    facts = " ".join(game_mode.move_facts(state))
    assert "5...Nf6" in facts and "knight from g8 to f6" in facts
    assert "the knight on f6 attacks the white pawn on e4" in facts
    assert "queen on d4" not in facts.split("is attacked by")[0]  # the queen is told only as what attacks the knight
    assert "6.Bd2" in facts and "the moved piece attacks no enemy piece" in facts
    assert "is not attacked" not in facts and "attacks nothing" not in facts.replace('"attacks nothing"', "")


def test_a_capture_and_the_better_move_are_told_with_the_piece_taken():
    moves = "e4 e5 Nf3 Nf6 Nc3 Bb4 Bc4 O-O O-O d6 d3 h6 h3 d5 Nxd5 Nc6 Nxb4".split()
    note = {"ply": 16, "san": "Nc6", "verdict": "blunder", "cp_loss": 340, "eval_after": -550, "best": "Nxd5"}
    assert game_mode._better_words(_state(moves, "black", [note]), note) == " — knight from f6 to d5, takes the knight on d5"
    from src.hypothetical import moved_piece_facts

    before = game_mode._replay(moves[:15])
    move = before.parse_san("Nxd5")
    after = before.copy(stack=False)
    after.push(move)
    facts = moved_piece_facts(before, after, move)
    assert facts[0] == "it takes the white knight on d5"
    assert any("an even trade" in f and "material stays level" not in f for f in facts)


def test_who_stands_better_is_said_in_words():
    assert "WORSE" in game_mode.student_eval_words(-200) and "2.0 pawns" in game_mode.student_eval_words(-200)
    assert "stands better" in game_mode.student_eval_words(150)
    assert "about equal" in game_mode.student_eval_words(30)


def test_an_attack_the_move_did_not_make_is_cut_from_the_comment():
    gate = _gate(GAME_1, "black")
    assert _issues(gate, "Хорошо: ходом 5...Nf6 ты развил коня и напал на ферзя.")
    assert not _issues(_gate(GAME_1, "black"), "Хорошо: ходом 5...Nf6 ты развил коня и напал на пешку e4.")


def test_a_sentence_true_after_the_reply_is_kept():
    moves = "e3 Nf6 d4 Nh5 Qxh5 e6 Nc3 c6 h4 b5 e4 a5 Qf3 Ba3 bxa3 a4 Bf4 Qxh4 Rxh4 d6 O-O-O Kf8 Nxb5".split()
    text = "Ты сыграл Kf8, и теперь мой конь спокойно забрал пешку на b5 и смотрит на твою пешку d6."
    assert not _issues(_gate(moves, "black"), text)


def test_the_comment_surface_can_be_put_back_to_recording_only(monkeypatch):
    from src import config

    monkeypatch.setattr(config, "COACH_COMMENT_RELATION_CHECK", "shadow")
    assert not _issues(_gate(GAME_1, "black"), "Хорошо: ходом 5...Nf6 ты развил коня и напал на ферзя.")


@pytest.mark.parametrize("text, flagged", [
    ("Хорошо сыграно: ты вернул фигуру и сохранил преимущество.", True),
    ("У тебя сейчас преимущество.", True),
    ("Ты упустил преимущество.", False),
    ("Теперь у белых преимущество.", False),
    ("Чтобы получить преимущество, тебе нужно закончить развитие.", False),
    ("У тебя нет преимущества.", False),
    ("Хороший ход, ты развил коня.", False),
])
def test_an_advantage_the_student_does_not_have(text, flagged):
    moves = "e4 e5 Nf3 Nc6 Bc4 Nf6 Ng5 d5 exd5 Na5".split()
    assert bool(_issues(_gate(moves, "black", engine_eval=2.0), text)) is flagged
    if flagged:
        assert not _issues(_gate(moves, "black", engine_eval=-1.0), text)  # the student is better: nothing to cut


# ── 4: the game before this one ───────────────────────────────────────────────────────────────────────────────────
PRIOR = "e4 e5 Nf3 Nf6 Nc3 Bb4 Bc4 O-O O-O d6 d3 h6 h3 d5 Nxd5 Nc6 Nxb4 Nxb4 c3".split()


def _prior_state():
    return {"student_color": "black", "moves": list(PRIOR), "status": "finished", "result": "1-0",
            "termination": "resign", "winner": "engine", "finished_at": 50.0,
            "annotations": [{"ply": 16, "san": "Nc6", "verdict": "blunder", "cp_loss": 340, "eval_after": -550,
                             "best": "Nxd5"}]}


@pytest.mark.parametrize("words, named", [
    ("А что было бы если бы я в прошлой партии взял конем на d5", True),
    ("в предыдущей игре я зевнул ферзя?", True),
    ("What if I had taken on d5 in the previous game?", True),
    ("өткен партияда қай жерде қателестім?", True),
    ("а если я сейчас возьму конём на d5?", False),
    ("покажи партию Морфи", False),
])
def test_the_words_that_name_the_previous_game(words, named):
    assert prior_game.names_prior_game(words) is named


def test_the_idea_is_placed_at_its_moment_of_the_previous_game():
    at = prior_game.moment("А что было бы если бы я в прошлой партии взял конем на d5", _prior_state())
    assert at and at["prior"] and at["played"] == "Nc6" and at["number"] == 8 and at["color"] == chess.BLACK
    assert chess.Board(at["fen"]).piece_at(chess.D5) == chess.Piece(chess.KNIGHT, chess.WHITE)
    assert "PREVIOUS game" in at["label"] and "8...Nc6" in at["label"]
    assert prior_game.moment("какую фигуру я зевнул в прошлой партии?", _prior_state()) is None


def test_the_previous_game_is_given_whole():
    state = _prior_state()
    at = prior_game.moment("в прошлой партии взял бы конём на d5", state)
    text = prior_game.block(state, at)
    assert text.startswith(prior_game.HEADER) and "never ask them for its moves" in text
    assert "1.e4 e5 2.Nf3 Nf6" in text and "8...Nc6" in text and "Nxd5" in text
    assert "The student played black" in text and "1-0" in text and at["fen"] in text


def test_the_previous_game_is_the_latest_finished_one_not_the_board():
    live = NS(id="b2", kind="game", game_state={"status": "playing", "moves": ["e4"]}, updated_at=90)
    old = NS(id="b0", kind="game", game_state={**_prior_state(), "finished_at": 10.0}, updated_at=95)
    last = NS(id="b1", kind="game", game_state=_prior_state(), updated_at=60)
    session = NS(boards=[old, last, live])
    assert prior_game.prior_board(session, live) is last
    assert prior_game.prior_board(session, last) is old
    assert prior_game.prior_board(NS(boards=[live]), live) is None


# ── 6: the session's name ─────────────────────────────────────────────────────────────────────────────────────────
def _user(text, at=3.0):
    return NS(role="user", content=text, timestamp=at)


def _coach(text, at=4.0):
    return NS(role="assistant", content=text, timestamp=at)


def _session(messages, boards=()):
    return NS(messages=list(messages), boards=list(boards))


GAME_BOARD = NS(kind="game", pgn="1. e4 c5 2. Nf3 d6 0-1", game_state={"result": "0-1"}, updated_at=9, created_at=2.0)


def test_a_service_text_does_not_name_the_session():
    text = ("Current chess puzzle context: This puzzle focuses on: middlegame, advantage, short. themes White to move. "
            "The solution is: Bxc6+ bxc6 Qxh6\n\nКакой лучший ход?")
    assert session_label.label(_session([_user(text)])) == "Какой лучший ход?"
    assert session_label.own_words("Current chess puzzle context: themes") == ""


def test_a_game_session_is_not_named_by_the_hint_button():
    hint = _user("Подскажи, на что обратить внимание в этой позиции (без лучшего хода).", at=5.0)
    assert session_label.label(_session([hint, _coach("…")], [GAME_BOARD])) == "1.e4 c5 2.Nf3 d6 0-1"
    assert session_label.label(_session([_user("давай сыграем", at=1.0)], [GAME_BOARD])) == "давай сыграем"


def test_a_pasted_position_names_the_session_only_when_nothing_was_said():
    fen = "7k/5Q2/6K1/8/8/8/8/8 b - - 0 1"
    assert session_label.label(_session([_user(fen), _coach("…"), _user("Почему тут ничья?", 6)])) == "Почему тут ничья?"
    assert session_label.label(_session([_user(fen)])) == fen
    assert session_label.is_board_paste("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0")
    assert session_label.is_board_paste("https://lichess.org/abcd1234")
    assert not session_label.is_board_paste("Разбери партию 1. e4 e5 2. Nf3")
    assert not session_label.is_board_paste("e4")


# ── 7: the next lesson ────────────────────────────────────────────────────────────────────────────────────────────
def _programme():
    def lesson(i, needs=None):
        return {"id": f"l{i}", "slug": f"s{i}", "title": f"Урок {i}", "order_index": i, "requires_lesson_id": needs}

    return {"courses": [
        {"id": "c1", "slug": "basics", "title": "Основы", "modules": [
            {"id": "m1", "title": "М1", "lessons": [lesson(1), lesson(2, "l1"), lesson(3, "l2")]},
            {"id": "m2", "title": "М2", "lessons": [lesson(4, "l3"), lesson(5)]}]},
        {"id": "c2", "slug": "tactics", "title": "Тактика", "modules": [
            {"id": "m3", "title": "М3", "lessons": [lesson(6), lesson(7)]}]},
    ]}


def _done(*ids):
    return {i: {"lesson_id": i, "status": "completed", "updated_at": "2026-11-23"} for i in ids}


def test_the_next_lesson_is_the_learn_pages_not_the_one_opened_last():
    progress = {**_done("l1", "l2"), "l5": {"lesson_id": "l5", "status": "in_progress", "updated_at": "2026-11-25"}}
    assert lp.next_lesson(_programme(), progress)[2]["id"] == "l3"
    began = lp.started_lesson(_programme(), progress, but="l3")
    assert began and began[2]["id"] == "l5"


def test_a_lesson_started_behind_a_closed_one_is_not_told():
    progress = {**_done("l1"), "l4": {"lesson_id": "l4", "status": "in_progress", "updated_at": "2026-11-25"}}
    assert lp.next_lesson(_programme(), progress)[2]["id"] == "l2"
    assert lp.started_lesson(_programme(), progress, but="l2") is None  # l4 needs l3
    assert not lp.lesson_open({"requires_lesson_id": "l3"}, progress) and lp.lesson_open({"id": "x"}, progress)


def test_the_course_is_the_one_part_way_through_and_locked_courses_are_skipped():
    progress = _done("l6")  # a student placed higher: the second course is theirs
    assert lp.next_lesson(_programme(), progress)[2]["id"] == "l7"
    assert lp.next_lesson(_programme(), {})[2]["id"] == "l1"
    assert lp.next_lesson(_programme(), _done("l1", "l2", "l3", "l4", "l5"), {"c2": {"locked": True}}) is None
    assert lp.next_lesson(_programme(), _done("l1", "l2", "l3", "l4", "l5"))[2]["id"] == "l6"


# ── 8: a rule's example; the warm-up's break ──────────────────────────────────────────────────────────────────────
def test_every_rule_example_is_what_it_says():
    assert rule_examples.EXAMPLES and all(rule_examples.verify(e) for e in rule_examples.EXAMPLES)


def test_en_passant_is_shown_with_its_own_example():
    rule = rule_examples.for_words("Что такое взятие на проходе, покажи на доске")
    assert rule and rule["key"] == "en_passant"
    assert rule_examples.for_words("What is en passant?")["key"] == "en_passant"
    assert rule_examples.for_words("как ходит конь") is None
    shown = rule_examples.topic(rule, "ru", show=True)
    assert shown["title"] == "Взятие на проходе" and shown["example"]["key_move"] == "exd6"
    assert shown["board_actions"][0] == {"type": "set_fen", "fen": rule["fen"]}
    arrows = shown["board_actions"][1]["arrows"]
    assert {"from": "e5", "to": "d6", "brush": "green"} in arrows and {"from": "d7", "to": "d5", "brush": "blue"} in arrows
    told = rule_examples.topic(rule, "en", show=False)
    assert "board_actions" not in told and told["title"] == "En passant"


def test_a_locked_lesson_about_a_rule_still_gives_the_rule():
    from src.learn_access import LOCKED_NOTE, LOCKED_RULE_NOTE

    assert "not a question" in LOCKED_NOTE and "OWN example" in LOCKED_RULE_NOTE


class _WarmSession(NS):
    def user_turns(self):
        return sum(1 for m in self.messages if m.role == "user")

    def active_board(self):
        return self.boards[0]


def _warm(board_fen, messages=()):
    start = "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1"
    state = {"ids": ["p1", "p2", "p3", "p4", "p5"], "lines": {"p4": [warmup._key(start)]}, "at": 3, "over": False}
    return _WarmSession(warmup=state, boards=[NS(kind="study", fen=board_fen or start)], messages=list(messages)), start


def test_an_example_put_over_the_warm_up_is_said_in_that_answer():
    session, _ = _warm(None, [_user("что такое рокировка, покажи")])
    result = {"board_actions": [{"type": "set_fen", "fen": rule_examples.EXAMPLES[1]["fen"]}]}
    warmup.left_for(session, result)
    assert "puzzle 4 of 5" in result["warmup_note"] and session.warmup["paused_said"]
    session.boards[0].fen = rule_examples.EXAMPLES[1]["fen"]
    session.messages.append(_coach("Рокировка — это… Разминка на паузе: задача 4 из 5, «дальше» вернёт её."))
    assert warmup.paused(session) is None  # said by the coach: not again


def test_the_server_says_the_break_when_the_coach_did_not():
    session, _ = _warm(None, [_user("что такое рокировка, покажи")])
    warmup.left_for(session, {"board_actions": [{"type": "set_fen", "fen": rule_examples.EXAMPLES[1]["fen"]}]})
    session.boards[0].fen = rule_examples.EXAMPLES[1]["fen"]
    session.messages.append(_coach("Рокировка — это ход короля и ладьи."))
    assert warmup.paused(session) == {"n": 4, "of": 5}


def test_a_puzzle_of_the_warm_up_itself_is_no_break():
    session, start = _warm(None)
    result = {"board_actions": [{"type": "set_puzzle", "fen": start, "puzzle_id": "p4"}]}
    warmup.left_for(session, result)
    assert "warmup_note" not in result and not session.warmup.get("paused_said")
    arrows_only = {"board_actions": [{"type": "draw_arrows", "arrows": []}]}
    warmup.left_for(session, arrows_only)
    assert "warmup_note" not in arrows_only


def test_the_topic_tool_gives_the_rule_example_only_when_the_lookup_has_nothing_of_the_rule(monkeypatch):
    import json

    from src.tools import knowledge_topics as kt
    from src.tools import registry

    handler = registry.get_entry("get_topic").handler
    by_a_shared_word = {"ambiguous": True, "topics": [{"slug": "passed-pawn", "title": "Проходная пешка"}]}
    monkeypatch.setattr(kt, "get_topic", lambda *a, **k: dict(by_a_shared_word))
    out = json.loads(handler({"topic": "взятие на проходе"}))
    assert out.get("source") == "rule_example" and out["slug"] == "en_passant" and out["board_actions"]
    # the base's own topics of the rule: the model picks one, as before
    own = {"ambiguous": True, "topics": [{"slug": "castling-when", "title": "Когда делать рокировку"}]}
    monkeypatch.setattr(kt, "get_topic", lambda *a, **k: dict(own))
    assert json.loads(handler({"topic": "castling"})).get("ambiguous")
    # a lookup that has its own example keeps it
    monkeypatch.setattr(kt, "get_topic", lambda *a, **k: {"slug": "x", "example": {"fen": "8/8/8/8/8/8/8/K1k5 w - - 0 1"}})
    assert json.loads(handler({"topic": "взятие на проходе"}))["slug"] == "x"
