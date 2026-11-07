"""Review 06.11 of the loaded-game facts (src/game_story.py) and of the arrows on the voice path.

* how a game ended is told only as far as the score establishes it — «Black resigned» was said of every 1-0;
* a promoted piece taken is the pawn it was (1.dxc8=Q+ Rxc8: White won a bishop for a pawn, not Black a queen);
* the ending is named by the pieces both sides have (rook against pawns is no rook ending);
* a lead in pieces («лишнее качество», «лишняя фигура») is judged on the pieces, not on points;
* the trade check cancels the pieces both sides took in a window, as the facts do;
* an ending avoided, aimed at or feared is no ending reached; «в итоге перешла в …» is «eventually»;
* the record a rewrite is proved by (told_game_plies) does not depend on the shadow facts check;
* the voice coach's arrows are judged on the position the student's board shows (a live game browsed back).
"""

import io

import chess
import chess.pgn
import pytest

from src import answer_check_db as acd
from src import config
from src.answer_check import check_sentence
from src.game_story import GameStory, ending_name

from tests.unit.test_game_story_2026_11_06 import (NAKAMURA_CARLSEN, NAKAMURA_SINDAROV, _arrows, _ctx, _pgn)


@pytest.fixture
def check_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_LOADED_GAME_CHECK", "on")


def _story(pgn):
    story = GameStory.from_pgn(pgn)
    assert story is not None, "the test game does not parse"
    return story


# ── how the game ended ───────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_a_decisive_result_is_not_told_as_a_resignation():
    story = _story(_pgn("1.e4 e5 2.Nf3 Nc6", result="1-0"))
    assert story.ending() == ("White won (1-0); the score stops after 2...Nc6 — the PGN does not say whether by "
                              "resignation or on time")


@pytest.mark.unit
def test_the_termination_header_is_told():
    pgn = _pgn("1.e4 e5 2.Nf3 Nc6", result="1-0").replace('[Result "1-0"]', '[Result "1-0"]\n[Termination "Time forfeit"]')
    assert _story(pgn).ending() == "Black lost on time after 2...Nc6 (1-0)"
    normal = _pgn("1.e4 e5 2.Nf3 Nc6", result="0-1").replace('[Result "0-1"]', '[Result "0-1"]\n[Termination "Normal"]')
    assert _story(normal).ending() == "White resigned after 2...Nc6 (0-1)"


@pytest.mark.unit
def test_a_draw_is_told_by_what_the_board_shows():
    bare = _pgn("1.Na3 Kb7 2.Nb5 Kc6 3.Na3", "k7/8/8/8/8/8/8/1N4K1 w - - 0 1", "1/2-1/2")
    assert _story(bare).ending() == "a draw after 3.Na3: neither side has the material left to mate"
    # a repetition claimed before the third time is not «a draw by repetition», nor «agreed»
    twice = _pgn("1.Nf3 Nf6 2.Ng1 Ng8 3.Nf3", result="1/2-1/2")
    assert _story(twice).ending() == "a draw after 3.Nf3; the PGN does not say how (agreed or claimed)"
    assert "a draw by repetition" in _story(NAKAMURA_SINDAROV).ending()


# ── a promoted piece taken ────────────────────────────────────────────────────────────────────────────────────────

DECOY = _pgn("1.dxc8=Q+ Rxc8", "r1b3k1/3P1ppp/8/8/8/8/5PPP/6K1 w - - 0 1", white="Nakamura,Hi", black="Carlsen,M")
KING_TAKES = _pgn("1.d8=Q+ Kxd8", "4k3/3P4/8/8/8/8/8/4K3 w - - 0 1")


@pytest.mark.unit
def test_a_promoted_piece_taken_is_the_pawn_it_was():
    assert _story(DECOY).exchange_lines() == ["1.dxc8=Q+ 1...Rxc8: White won a bishop for a pawn; material after it: "
                                              "Black up 5"]
    assert _story(KING_TAKES).exchange_lines() == ["1...Kxd8: Black won a pawn; material after it: level"]


@pytest.mark.unit
def test_a_promoted_piece_that_moved_on_is_still_the_pawn():
    # 1.d8=Q+ Kf7 2.Qd7+ Kf8 3.Qe7+ Kxe7 — the queen that was a pawn, taken on another square
    pgn = _pgn("1.d8=Q+ Kf7 2.Qd7+ Kf8 3.Qe7+ Kxe7", "5k2/3P4/8/8/8/8/8/4K3 w - - 0 1")
    assert _story(pgn).exchange_lines() == ["3...Kxe7: Black won a pawn; material after it: level"]


@pytest.mark.unit
def test_the_check_reads_a_promoted_piece_as_a_pawn(check_on):
    assert check_sentence("Накамура провёл пешку и выиграл слона за пешку.", _ctx(DECOY)) == []
    issues = check_sentence("В партии чёрные выиграли ферзя за слона.", _ctx(DECOY))
    assert issues and "White won a bishop for a pawn" in issues[0]


# ── the ending's name ─────────────────────────────────────────────────────────────────────────────────────────────

ROOK_V_PAWNS = _pgn("1.Rxb8+ Kg7", "1r5k/1R5p/8/8/8/8/6PP/6K1 w - - 0 1")


@pytest.mark.unit
def test_rook_against_pawns_is_no_rook_ending():
    story = _story(ROOK_V_PAWNS)
    assert ending_name(story.boards[-1]) == "rook v no pieces"
    assert story.phase_lines()[-1] == ("from 1.Rxb8+, to the end of the game: rook v no pieces; pawns 2–1; White up a "
                                       "rook and a pawn")
    assert ending_name(chess.Board("1r5k/6pp/8/8/8/8/1R4PP/6K1 w - - 0 1")) == "a rook ending (rooks and pawns only)"


@pytest.mark.unit
def test_rook_against_pawns_is_not_judged_a_rook_ending(check_on):
    issues = check_sentence("Партия закончилась ладейным эндшпилем.", _ctx(ROOK_V_PAWNS))
    assert issues and any("the game ended with rook v no pieces" in i for i in issues), issues


# ── a lead in pieces ──────────────────────────────────────────────────────────────────────────────────────────────

# R+5P v B+6P, held to the end: up 1 in points, up the exchange in pieces.
EXCHANGE_UP = _pgn("1.Kf1 Kf8 2.Ke2 Ke7 3.Kd2 Kd6 4.Kc3 Kc5", "6k1/pp3ppp/2b1p3/8/8/8/PP3PPP/4R1K1 w - - 0 1", "1-0",
                   white="Nakamura,Hi", black="Carlsen,M")


@pytest.mark.unit
def test_the_facts_say_the_pieces_behind_a_lead():
    facts = _story(EXCHANGE_UP).facts()
    assert "White up 1 (White up the exchange for a pawn) from the start, to the end of the game" in facts


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "Накамура долго играл с лишним качеством.",
    "В этой партии белые остались с лишним качеством и выиграли.",
    "В итоге у белых было лишнее качество.",
])
def test_an_exchange_up_for_a_pawn_is_an_extra_exchange(check_on, sentence):
    assert check_sentence(sentence, _ctx(EXCHANGE_UP)) == []


@pytest.mark.unit
def test_a_piece_the_side_never_had_is_still_cut(check_on):
    issues = check_sentence("Накамура долго играл с лишней фигурой.", _ctx(EXCHANGE_UP))
    assert any("never led by a piece" in i for i in issues), issues
    issues = check_sentence("В итоге у чёрных было лишнее качество.", _ctx(EXCHANGE_UP))
    assert any("it ended White up the exchange for a pawn" in i for i in issues), issues


# ── trades: the pieces both sides took cancel ─────────────────────────────────────────────────────────────────────

NETTED = _pgn("1.Rxd5 Nxe4 2.Bxe4 Rxd5", "3r2k1/5ppp/5n2/3q4/4N3/5B2/5PPP/3R2K1 w - - 0 1", white="Nakamura,Hi",
              black="Carlsen,M")


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "В партии Накамура выиграл ферзя за ладью.",
    "Белые выиграли ферзя за ладью, по ходу разменяв коней.",
    "Белые выиграли ферзя и коня за ладью и коня.",
])
def test_a_trade_said_as_the_facts_say_it_passes(check_on, sentence):
    assert "knights traded; White won a queen for a rook" in _story(NETTED).facts()
    assert check_sentence(sentence, _ctx(NETTED)) == []


@pytest.mark.unit
def test_a_wrong_trade_is_still_cut_after_netting(check_on):
    issues = check_sentence("Белые выиграли ферзя за коня.", _ctx(NETTED))
    assert issues and "no exchange of it was that" in issues[0]


# ── endings avoided, aimed at; «в итоге» of a transition ─────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("pgn,sentence", [
    (NAKAMURA_SINDAROV, "В этой партии Накамура избежал ладейного эндшпиля, сохранив коня."),
    (NAKAMURA_SINDAROV, "В этой партии белые уклонились от размена в ладейный эндшпиль."),
    (NAKAMURA_SINDAROV, "В этой партии Синдаров стремился к ладейному эндшпилю, но Накамура сохранил коня."),
    (NAKAMURA_SINDAROV, "В этой партии Синдаров стремился перевести игру в ладейный эндшпиль."),
    (NAKAMURA_CARLSEN, "В этой партии Карлсен избежал разноцветных слонов."),
])
def test_an_ending_avoided_or_aimed_at_is_not_judged(check_on, pgn, sentence):
    assert check_sentence(sentence, _ctx(pgn)) == []


# A rook ending for 8 plies, won by 6.bxc8=Q+.
ROOK_WON = _pgn("1.Kf3 Kg7 2.Ke4 Kg6 3.Kd5 Kg5 4.Kd6 Kg4 5.Kd7 Kg3 6.bxc8=Q", "2r5/1P5k/8/8/8/8/R5K1/8 w - - 0 1",
                "1-0", white="Nakamura,Hi", black="Carlsen,M")


@pytest.mark.unit
@pytest.mark.parametrize("sentence", [
    "В итоге партия перешла в ладейный эндшпиль.",
    "В итоге партия свелась к ладейному эндшпилю, который Накамура выиграл.",
    "В итоге получился ладейный эндшпиль.",
])
def test_eventually_went_into_a_rook_ending_won_by_promoting(check_on, sentence):
    assert "a rook ending" in _story(ROOK_WON).facts()
    assert check_sentence(sentence, _ctx(ROOK_WON)) == []


@pytest.mark.unit
def test_ended_in_a_rook_ending_is_still_the_final_position(check_on):
    issues = check_sentence("Партия закончилась ладейным эндшпилем.", _ctx(ROOK_WON))
    assert issues and "the game ended with" in issues[0]


# ── the rewrite's record does not depend on the shadow facts check ───────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("mode", ["shadow", "on"])
def test_told_game_plies_reads_the_moves_only(monkeypatch, mode):
    monkeypatch.setattr(config, "COACH_LOADED_GAME_CHECK", mode)
    plain = acd.told_game_plies("На 18-м ходу Накамура забрал пешку d5.", _ctx(NAKAMURA_SINDAROV))
    told = acd.told_game_plies("На 18-м ходу Накамура забрал пешку d5, а позже партия перешла в ладейный эндшпиль.",
                               _ctx(NAKAMURA_SINDAROV))
    assert plain and told and [san for _, _, san in told] == ["Qxd5"]


# ── voice arrows on the position the student sees ───────────────────────────────────────────────────────────────

GAME = "1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Nxe4 5. Re1 Nd6 6. Nxe5 Be7 7. Bf1 Nf5 8. Nf3 d5"


def _live_session():
    from src.boards import new_board

    game = chess.pgn.read_game(io.StringIO(GAME))
    board = game.board()
    boards = [board.fen()]
    for move in game.mainline_moves():
        board.push(move)
        boards.append(board.fen())
    rec = new_board("s1", kind="game", pgn=GAME)
    rec.fen, rec.ply = board.fen(), len(boards) - 1

    class _Session:
        board_state = rec.fen

        def active_board(self):
            return rec

    return _Session(), boards


@pytest.mark.unit
def test_a_live_game_browsed_back_keeps_the_arrow_of_the_shown_move():
    from src.tool_bridge import _prune_voice_arrows

    session, boards = _live_session()
    # the student browsed back to ply 7 (before 4...Nxe4): f6→e4 is the move they look at — the page says so
    kept, dropped = _prune_voice_arrows([_arrows(("f6", "e4"))], session, boards[7])
    assert dropped == [] and kept[0]["arrows"]
    # an old page sends no position: the live game's board is not judged by the game's moves (it may be browsed)
    kept, dropped = _prune_voice_arrows([_arrows(("f6", "e4"))], session)
    assert dropped == [] and kept[0]["arrows"]
    # shown the live position, the past move is another position's (the knight left e4 by 5...Nd6)
    kept, dropped = _prune_voice_arrows([_arrows(("f6", "e4"))], session, boards[-1])
    assert kept == [] and dropped[0].startswith("f6e4: it is the game's move 4...Nxe4")
    # the piece rule on the shown position: at ply 7 the knight on f6 cannot go to f4
    kept, dropped = _prune_voice_arrows([_arrows(("f6", "f4"))], session, boards[7])
    assert kept == [] and "knight cannot go there" in dropped[0]
    # a broken position from the page is ignored
    kept, dropped = _prune_voice_arrows([_arrows(("f6", "e4"))], session, "not a fen")
    assert dropped == [] and kept[0]["arrows"]
