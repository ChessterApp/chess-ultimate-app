"""The review's words and its card are one fact (tester's report 17.11, fixed 18.11).

A game loaded from Lichess, «Разбери эту партию»: the coach's text said the game had three key moments, all around
move 30, over a card titled «Разбор партии · 6 моментов» whose first moment was move 5 — a move the text never
named. Both came from one scan, apart: the card lists every moment with a better move to find
(src/review_moments.build_review_moments), the text was the model's pick of «the turning points that matter most»
with its own count, and nothing told the model the card was there. Now the card is built first: the answer opens
with the server's own line — the card's count and its moves —, the model is told the same list, which of the
moments to explain (the biggest swings, picked by the server) and that the others are on the card.
"""

import json

import chess
import pytest

from src import config
from src.prompt_builder import review_block
from src.review_moments import (MAIN_MOMENTS, build_review_moments, card_moments, card_note, main_moments,
                                moments_line, played_label)

pytestmark = pytest.mark.unit

GAME = ("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6 8. c3 O-O 9. h3 Nb8 "
        "10. d4 Nbd7 *")


def _white(number, before, after):
    """White missed Ra8# on move *number* and played Kf2."""
    return {"move_number": number, "side": "white", "move": "Kf2", "eval_before": before, "eval_after": after,
            "type": "mistake", "fen_before": f"6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 {number}", "best_move": "Ra8#",
            "best_line": "Ra8#"}


def _black(number, before, after):
    """Black left the queen on d5 alone on move *number* and played Kf8."""
    return {"move_number": number, "side": "black", "move": "Kf8", "eval_before": before, "eval_after": after,
            "type": "mistake", "fen_before": f"3rk3/8/8/3Q4/8/8/8/4K3 b - - 0 {number}", "best_move": "Rxd5",
            "best_line": "Rxd5"}


# The tester's game in small: six moments, the first on move 5, the three biggest swings around move 30.
SCAN = {"total_moves": 80, "engine_depth": 12, "evals_from": "white", "critical_moments": [
    _white(5, 0.5, -1.2), _black(12, -0.2, 1.6), _white(18, 1.0, -0.9),
    _white(30, 0.3, -4.0), _black(31, -3.0, 2.5), _white(33, 2.0, -6.0)]}
MOVES = ["5.Kf2", "12...Kf8", "18.Kf2", "30.Kf2", "31...Kf8", "33.Kf2"]


def _card(scan=SCAN, **kw):
    return build_review_moments(scan, pgn=GAME, **kw)


# ── the card is the list ────────────────────────────────────────────────────────────────────────

def test_the_cards_moments_are_named_as_the_card_names_them():
    """«5.Kf2», «12...Kf8»: the move with its number, in the game's order — what the card's own texts write."""
    card = _card()
    assert [played_label(m) for m in card_moments(card)] == MOVES
    assert card_moments(None) == [] and card_moments({"kind": "critical_moments", "moments": [{}]}) == []


def test_the_biggest_swings_are_picked_by_the_server():
    """Which moments «matter most» is the engine's swing, counted here — for White and for Black alike."""
    assert [played_label(m) for m in main_moments(_card())] == ["30.Kf2", "31...Kf8", "33.Kf2"]
    small = {**SCAN, "critical_moments": SCAN["critical_moments"][:MAIN_MOMENTS]}
    assert [played_label(m) for m in main_moments(_card(small))] == MOVES[:MAIN_MOMENTS]   # a short card: all of it


# ── the server's line ───────────────────────────────────────────────────────────────────────────

def test_the_servers_line_gives_the_cards_count_and_its_moves():
    """The first line of the answer: six moments on the card — six in the text, with move 5 among them."""
    card = _card()
    assert moments_line(card, "ru") == "В разборе партии 6 моментов: " + ", ".join(MOVES) + "."
    assert moments_line(card, "en") == "The review of the game has 6 moments: " + ", ".join(MOVES) + "."
    assert moments_line(card, "kk") == moments_line(card, "kz") == \
        "Партия талдауында 6 сәт бар: " + ", ".join(MOVES) + "."


@pytest.mark.parametrize("count,ru,en", [(1, "1 момент", "1 moment"), (2, "2 момента", "2 moments"),
                                         (4, "4 момента", "4 moments"), (5, "5 моментов", "5 moments")])
def test_the_count_is_said_in_the_languages_own_grammar(count, ru, en):
    card = _card({**SCAN, "critical_moments": SCAN["critical_moments"][:count]})
    assert moments_line(card, "ru").startswith(f"В разборе партии {ru}: 5.Kf2")
    assert moments_line(card, "en").startswith(f"The review of the game has {en}: 5.Kf2")


def test_read_aloud_the_line_is_the_count_alone():
    """The voice pipeline reads the answer out: a row of moves in notation is not said, the count is."""
    assert moments_line(_card(), "ru", spoken=True) == "В разборе партии 6 моментов."
    assert moments_line(_card(), "en", spoken=True) == "The review of the game has 6 moments."


def test_no_card_no_line():
    """A clean game, or moments with no better move to find (no card is shown): the server writes nothing."""
    assert moments_line(None, "ru") == "" and moments_line({"kind": "critical_moments", "moments": []}, "ru") == ""
    assert card_note(None) == ""


# ── what the model is told ──────────────────────────────────────────────────────────────────────

def test_the_block_names_the_cards_moments_their_count_and_the_ones_to_explain():
    """The model no longer picks and counts on its own: the card's six moments by name, the three biggest to
    explain, the other three on the card — and never another number."""
    block = review_block(SCAN, card=_card(), told=True)
    assert "exactly 6 moments" in block and ", ".join(MOVES) in block
    assert "never give another number of moments" in block
    assert "only the 3 biggest swings — 30.Kf2, 31...Kf8, 33.Kf2" in block
    assert "the other 3 (5.Kf2, 12...Kf8, 18.Kf2) are on the card" in block
    assert "ALREADY written the first line" in block and "Say first" not in block
    assert "turning points that matter most" not in block          # the old «pick for yourself»


def test_a_model_that_writes_the_whole_answer_is_told_to_say_the_count():
    """Its own scan call, the voice coach: no server line stands before its words — it says the card's count."""
    block = review_block(SCAN, card=_card())
    assert "Say first that the review has 6 moments" in block and "ALREADY written" not in block


def test_a_short_card_is_explained_whole():
    scan = {**SCAN, "critical_moments": SCAN["critical_moments"][3:5]}
    block = review_block(scan, card=_card(scan), told=True)
    assert "exactly 2 moments" in block and "Explain each of them" in block and "biggest swings" not in block


def test_a_swing_with_no_better_move_is_not_one_of_the_reviews_moments():
    """The scan lists a swing the engine names no better move for: it is not on the card, so the text does not
    count it either — five and five."""
    loose = dict(_white(22, 0.4, -1.4))
    del loose["best_move"], loose["best_line"]
    scan = {**SCAN, "critical_moments": sorted(SCAN["critical_moments"][:5] + [loose], key=lambda m: m["move_number"])}
    card = _card(scan)
    block = review_block(scan, card=card, told=True)
    assert len(card_moments(card)) == 5 and "exactly 5 moments" in block
    line = next(ln for ln in block.splitlines() if ln.startswith("- 22.Kf2"))
    assert "NOT on the student's card" in line
    assert sum("NOT on the student's card" in ln for ln in block.splitlines()) == 1


def test_swings_the_scan_did_not_keep_are_not_denied():
    """The scan keeps the biggest swings (src/tools/critical_moments.MAX_MOMENTS): «only six mistakes» is not said."""
    block = review_block({**SCAN, "moments_found": 9}, card=_card(), told=True)
    assert "found 9 swings" in block and "never say the game had only 6 mistakes" in block


def test_without_a_card_the_block_is_as_it_was():
    """No card under the answer (a clean game, an older caller): nothing is claimed about one."""
    block = review_block(SCAN)
    assert "turning points that matter most" in block and "review card" not in block
    assert "NOT on the student's card" not in block
    assert "no swing of 1.5 pawns" in review_block({"total_moves": 30, "critical_moments": []})


# ── the tools ───────────────────────────────────────────────────────────────────────────────────

def test_the_voice_review_note_follows_the_card_of_the_students_side(monkeypatch):
    """review_game (the voice page's call): the note is the same block, about the card of the side the student
    played — Black's two moments, White's four marked as not on it."""
    from src.tools import review_game as rg

    monkeypatch.setattr(rg, "find_critical_moments", lambda pgn: SCAN)
    out = rg.review_game(GAME, side="black")
    assert "exactly 2 moments" in out["note"] and "12...Kf8, 31...Kf8" in out["note"]
    assert "Say first that the review has 2 moments" in out["note"]
    assert sum("NOT on the student's card" in ln for ln in out["note"].splitlines()) == 4
    assert "exactly 6 moments" in rg.review_game(GAME)["note"]


def test_the_scan_tools_result_tells_the_model_about_the_card(monkeypatch):
    """find_critical_moments called by the model itself: the result carries the card's list with the moments."""
    from src.tools import critical_moments as cm

    monkeypatch.setattr(cm, "find_critical_moments", lambda pgn, threshold=1.5: dict(SCAN))
    out = json.loads(cm._handle_find_critical_moments({"pgn": GAME}))
    assert len(out["critical_moments"]) == 6
    assert "exactly 6 moments" in out["card_note"] and "Say first that the review has 6 moments" in out["card_note"]
    monkeypatch.setattr(cm, "find_critical_moments", lambda pgn, threshold=1.5: {"error": "Could not parse PGN."})
    assert json.loads(cm._handle_find_critical_moments({"pgn": "x"})) == {"error": "Could not parse PGN."}


# ── the turn ────────────────────────────────────────────────────────────────────────────────────

H = {"X-User-Id": "review-one-fact"}


@pytest.fixture
def turn(monkeypatch):
    """The text turn with the model and the scan replaced: (client, seen)."""
    from fastapi.testclient import TestClient

    from src import server
    from src.tools import critical_moments as cm

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-not-a-key")
    monkeypatch.setattr(config, "COACH_TWO_STAGE", False)
    monkeypatch.setattr(config, "COACH_TOOL_SUBSET", False, raising=False)
    monkeypatch.setattr(cm, "find_critical_moments", lambda pgn, *a, **k: dict(SCAN))
    monkeypatch.setattr(server, "_board_review_fits", lambda pgn: (True, {}))
    seen: dict = {}

    def fake_chat(agent, message, session_id, stream_callback=None, student_message="", game_step=False):
        seen["message"] = message
        if stream_callback:
            stream_callback("Главное случилось около тридцатого хода.")
        return "Главное случилось около тридцатого хода."

    monkeypatch.setattr(server, "_chat_in_session", fake_chat)
    yield TestClient(server.app), seen


def _say(client, sid, text, **kw):
    frames = []
    with client.stream("POST", "/api/coach/chat", json={"message": text, "session_id": sid, "locale": "ru", **kw},
                       headers=H) as r:
        for line in r.iter_lines():
            if line.startswith("data:"):
                frames.append(json.loads(line[5:]))
    return frames


def _review(client, **kw):
    sid = client.post("/api/coach/sessions", json={}, headers=H).json()["id"]
    client.post(f"/api/coach/sessions/{sid}/boards", json={"kind": "master_game", "pgn": GAME}, headers=H)
    frames = _say(client, sid, "Разбери эту партию", **kw)
    cards = [f["tool_result"]["summary"] for f in frames if isinstance(f.get("tool_result"), dict)
             and f["tool_result"].get("tool") == "find_critical_moments"]
    return "".join(f["delta"] for f in frames if "delta" in f), cards, sid


def test_the_answer_opens_with_the_count_and_the_moves_of_the_card_under_it(turn):
    """The tester's turn: the card has six moments from move 5 on — the text says six and names move 5, whatever
    the model goes on to explain; the model is told the line is there."""
    client, seen = turn
    text, cards, sid = _review(client)
    assert cards[0]["kind"] == "review_moments" and len(cards[0]["moments"]) == 6
    assert chess.Board(cards[0]["moments"][0]["fen"]).fullmove_number == 5
    assert text == "В разборе партии 6 моментов: " + ", ".join(MOVES) + ".\n\nГлавное случилось около тридцатого хода."
    assert "exactly 6 moments" in seen["message"] and "ALREADY written the first line" in seen["message"]
    stored = client.get(f"/api/coach/sessions/{sid}/messages", headers=H).json()["messages"][-1]["content"]
    assert stored == text


def test_spoken_the_answer_opens_with_the_count(turn):
    client, _ = turn
    text, cards, _ = _review(client, speech=True)
    assert text.startswith("В разборе партии 6 моментов.\n\n") and len(cards[0]["moments"]) == 6


def test_a_review_without_a_card_gets_no_line(turn, monkeypatch):
    """Moments the card cannot show (no better move that fits): no card, so no count of one in the text."""
    from src.tools import critical_moments as cm

    client, seen = turn
    monkeypatch.setattr(cm, "find_critical_moments", lambda pgn, *a, **k: {
        "total_moves": 20, "engine_depth": 12, "critical_moments": [{
            "move_number": 5, "side": "white", "move": "O-O", "eval_before": 0.3, "eval_after": -1.5,
            "type": "mistake", "fen_before": chess.STARTING_FEN, "best_move": "d4"}]})
    text, cards, _ = _review(client)
    assert text == "Главное случилось около тридцатого хода." and cards[0]["kind"] == "critical_moments"
    assert "review card" not in seen["message"] and "turning points that matter most" in seen["message"]
