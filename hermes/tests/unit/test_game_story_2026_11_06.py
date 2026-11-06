"""A loaded game told from its facts, and arrows on the position the board shows (06.11).

The live run of 04.11 on production (04.11-2, answers in local-preview/archive-1103/shipped-prod): the coach loaded
the database games it was asked for and told them from its own sums —
  * «партия перешла в ладейно-пешечное окончание» — Nakamura – Sindarov (3708548) ended rook and knight v rook and
    bishop; it never had rooks and pawns only;
  * «в итоге белые выиграли ферзя и ладью за ферзя и слона» — Nakamura – Carlsen (3686097): it was for a queen, a
    knight and a pawn (20...Bxd5 21.Nxd8 Bxf3 22.Ne6 Bd5 23.Nxf8 Kxf8);
  * «лишняя пешка» that held one move (18.Qxd5 … 19...Nxf2);
  * an arrow f3→e5 for 6.Nxe5 drawn on the final position of Sindarov – Nakamura (3708561), where f3 is empty.

The server now adds the game up (src/game_story.py): the material balance and how long it held, the exchanges as
pairs, the pieces left (the ending), the key moments — given to the model with get_game_pgn's moves, on the later
turns while the game is on the board, and to the rewrite; COACH_LOADED_GAME_CHECK reads the same claims in a sentence
against them. An arrow that is a move of the game on the board made on another position is not drawn
(src/board_markup.prune_board_actions, text and voice).
"""

import io
import json
import sqlite3

import chess
import chess.pgn
import pytest

from src import answer_check_db as acd
from src import config
from src.answer_check import CheckContext, check_sentence
from src.board_markup import arrow_verdicts, prune_board_actions
from src.game_story import GameStory, game_facts, story_issues
from src.tools import twic_search

NAKAMURA_SINDAROV = """[Event "Clutch Chess: Champions"]
[Date "2026.10.28"]
[White "Nakamura,Hi"]
[Black "Sindarov,Javokhir"]
[Result "1/2-1/2"]

1. e4 c5 2. Nf3 e6 3. g3 d5 4. exd5 exd5 5. d4 Nc6 6. Bg2 cxd4 7. O-O Bc5 8. Nbd2 Nf6 9. Re1+ Be6 10. Nb3 Bb6
11. Nfxd4 O-O 12. h3 Qd7 13. Kh2 Bf5 14. Bg5 Ne4 15. Be3 Bg6 16. Nxc6 Qxc6 17. Bxb6 Qxb6 18. Qxd5 Rad8 19. Qe5 Nxf2
20. Re2 Nd1 21. c3 h6 22. Qa5 Bd3 23. Qxb6 axb6 24. Rd2 Ne3 25. Nd4 Bc4 26. b3 Nxg2 27. Kxg2 Bd5+ 28. Kf2 Be6 29. h4
Rd6 30. Re1 Rc8 31. Rd3 b5 32. Ree3 Bd7 33. Ne2 Rf6+ 34. Rf3 Rxf3+ 35. Kxf3 Bc6+ 36. Kf2 Ra8 37. Rd2 Kf8 38. Nd4 Ke7
39. Ke3 Bd7 40. Re2 Kd6 41. Kf4 Rc8 42. Re3 Rc5 43. Rd3 Ke7 44. Re3+ Kd6 45. Rd3 Ke7 46. Re3+ Kd6 1/2-1/2
"""
NAKAMURA_CARLSEN = """[Event "1st 3-0 Thu 24th Sep 2026"]
[Date "2026.09.24"]
[White "Nakamura,Hi"]
[Black "Carlsen,M"]
[Result "1-0"]

1. e4 c5 2. Nf3 Nc6 3. Bb5 f6 4. d4 cxd4 5. Nxd4 e6 6. O-O Nge7 7. Be3 Ng6 8. Nd2 Be7 9. f4 O-O 10. c3 Nxd4 11. cxd4
f5 12. d5 a6 13. Bd3 b5 14. exf5 exf5 15. Qh5 d6 16. Nf3 Bf6 17. Nd4 Ne7 18. Rae1 g6 19. Qf3 Bb7 20. Ne6 Bxd5 21.
Nxd8 Bxf3 22. Ne6 Bd5 23. Nxf8 Kxf8 24. b3 Kf7 25. Rc1 Nc6 26. Rfd1 Ke6 27. Be2 Be4 28. Bf3 Nb4 29. Rd2 Nd5 30. Bd4
Bxf3 31. gxf3 Nxf4 32. Bxf6 Kxf6 33. Rxd6+ Kg5 34. Kf2 Re8 35. Rd2 h5 36. Re1 Nh3+ 37. Kf1 Rc8 38. Rg2+ Kf6 39. Rd1
Rc6 40. Rgd2 Kg5 41. Rd6 Rc2 42. R1d2 Rc1+ 43. Ke2 Nf4+ 44. Ke3 Rc3+ 45. Kd4 Rxf3 46. Rxa6 Kh4 47. Rb6 g5 48. Rxb5
Nh3 49. a4 g4 50. a5 Rf1 51. Ra2 f4 52. a6 Rd1+ 53. Kc5 Rd8 54. a7 Rc8+ 55. Kd6 f3 56. a8=Q f2 57. Qxc8 f1=Q 58.
Qd8+ 1-0
"""
SINDAROV_NAKAMURA = """[Event "Clutch Chess: Champions"]
[Date "2026.10.29"]
[White "Sindarov,Javokhir"]
[Black "Nakamura,Hi"]
[Result "1/2-1/2"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 Nf6 4. O-O Nxe4 5. Re1 Nd6 6. Nxe5 Be7 7. Bf1 Nf5 8. Nf3 d5 9. d4 O-O 10. c3 Bd6 11. Bd3
Nce7 12. Nbd2 c6 13. Nf1 g6 14. a4 Ng7 15. Ng3 Nef5 16. a5 Re8 17. Rxe8+ Qxe8 18. Bg5 Qf8 19. Qd2 f6 20. Bf4 Bxf4
21. Qxf4 Qd6 22. Qd2 Bd7 23. Re1 Nxg3 24. hxg3 Re8 25. Rxe8+ Nxe8 26. Ne1 Ng7 27. Nc2 Bf5 28. Bxf5 Nxf5 29. Ne3 Nxe3
30. Qxe3 Kf7 31. Qh6 Kg8 32. Qe3 Kf7 33. Qh6 Kg8 34. Qe3 Kf7 1/2-1/2
"""


def _final(pgn):
    game = chess.pgn.read_game(io.StringIO(pgn))
    board = game.board()
    for move in game.mainline_moves():
        board.push(move)
    return board


def _ctx(pgn):
    fen = _final(pgn).fen()
    ctx = CheckContext.from_fens([None, fen, fen], [pgn], question="Расскажи про эту партию")
    ctx.db_tracked = True
    acd.note_board_game(ctx, pgn)
    return ctx


@pytest.fixture
def check_on(monkeypatch):
    monkeypatch.setattr(config, "COACH_LOADED_GAME_CHECK", "on")


# ── the facts ──────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_the_facts_name_the_ending_by_the_pieces_left():
    facts = GameStory.from_pgn(NAKAMURA_SINDAROV).facts()
    assert "from 35.Kxf3, to the end of the game: rook and knight v rook and bishop; pawns 5–5" in facts
    assert "rook ending (rooks and pawns only)" not in facts.split("Pieces besides")[1]
    queens = GameStory.from_pgn(SINDAROV_NAKAMURA).facts()
    assert "from 30.Qxe3, to the end of the game: a queen ending (queens and pawns only); pawns 7–7" in queens


@pytest.mark.unit
def test_the_facts_tell_an_exchange_as_pairs():
    facts = GameStory.from_pgn(NAKAMURA_CARLSEN).facts()
    assert ("20...Bxd5 21.Nxd8 21...Bxf3 22.Ne6 22...Bd5 23.Nxf8 23...Kxf8: queens traded; White won a rook for a "
            "knight and a pawn; material after it: White up 1") in facts
    assert "56.a8=Q: White promotes to a queen" in facts and "57...f1=Q: Black promotes to a queen" in facts
    assert "The game ended: Black resigned after 58.Qd8+" in facts


@pytest.mark.unit
def test_the_facts_say_how_long_a_lead_held():
    facts = GameStory.from_pgn(NAKAMURA_SINDAROV).facts()
    assert "White up 1 after 18.Qxd5, for 3 plies, until 19...Nxf2" in facts
    # a capture taken straight back is no lead: 16.Nxc6 (White up 3 for one ply) is not told
    assert "White up 3" not in facts and "White up 9" not in facts
    assert "a draw by repetition" in facts


@pytest.mark.unit
def test_the_side_that_comes_out_ahead_is_the_one_that_won_the_exchange():
    assert GameStory.pairs([chess.PAWN, chess.PAWN], [chess.ROOK, chess.KNIGHT]) == \
        "Black won a rook and a knight for 2 pawns"
    assert GameStory.pairs([chess.QUEEN], [chess.QUEEN]) == "queens traded"


@pytest.mark.unit
def test_game_facts_never_raises_and_names_the_shown_position():
    assert game_facts("not a game") == ""
    note = game_facts(SINDAROV_NAKAMURA, 68)
    assert "The board shows the final position of this game, after 34...Kf7 (ply 68 of 68)" in note
    assert "an earlier position" in game_facts(SINDAROV_NAKAMURA, 10)


@pytest.mark.unit
def test_get_game_pgn_gives_the_facts_and_the_shown_position():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE games (id INTEGER PRIMARY KEY, white_name TEXT, black_name TEXT, result TEXT, date TEXT, "
                 "eco TEXT, event TEXT, white_elo INTEGER, black_elo INTEGER, pgn TEXT)")
    conn.execute("INSERT INTO games VALUES (3708548, 'Nakamura,Hi', 'Sindarov,Javokhir', '1/2-1/2', '2026.10.28', 'B40', "
                 "'Clutch Chess: Champions', 2792, 2782, ?)", (NAKAMURA_SINDAROV.split("\n\n", 1)[1],))
    out = twic_search.get_game_pgn(3708548, conn=conn)
    assert "rook and knight v rook and bishop" in out["facts"]
    assert "facts:" in out["note"]
    shown = twic_search._with_board(out)
    assert shown["board_shows"].startswith("The board shows the final position of this game, after 46...Kd6")


@pytest.mark.unit
def test_the_rewrite_hears_the_facts():
    ctx = _ctx(NAKAMURA_CARLSEN)
    assert "queens traded; White won a rook for a knight and a pawn" in acd.turn_tools_note(ctx)


# ── the check: the live run's sentences, and true ones beside them ────────────────────────────────────────────────

WRONG = [
    (NAKAMURA_SINDAROV, "Партия перешла в ладейно-пешечное окончание, где Накамура не смог реализовать перевес.",
     "never reached a rook ending"),
    (NAKAMURA_SINDAROV, "В итоге получился ладейный эндшпиль, и стороны разошлись миром.", "ended with rook and knight"),
    (NAKAMURA_CARLSEN, "В итоге белые выиграли ферзя и ладью за ферзя и слона.", "White won a rook for a knight"),
    (NAKAMURA_SINDAROV, "Накамура остался с лишней пешкой, но реализовать её не смог.", "held only 3 plies"),
    (NAKAMURA_SINDAROV, "Белые долго играли с лишней пешкой.", "held only 3 plies"),
    (NAKAMURA_SINDAROV, "В итоге у белых осталась лишняя пешка.", "it ended level"),
    (NAKAMURA_SINDAROV, "Синдаров отдал слона за коня на 26-м ходу.", "no exchange of it was that"),
    (NAKAMURA_CARLSEN, "Карлсен долго играл с лишней пешкой.", "Black"),
    (SINDAROV_NAKAMURA, "Партия свелась к ладейному эндшпилю.", "never reached a rook ending"),
    (SINDAROV_NAKAMURA, "In the end the game reached a rook ending.", "ended with a queen ending"),
    (NAKAMURA_CARLSEN, "White won a queen and a rook for a queen and a bishop.", "no exchange of it was that"),
]
RIGHT = [
    (NAKAMURA_SINDAROV, "Партия закончилась в окончании ладья и конь против ладьи и слона."),
    (NAKAMURA_SINDAROV, "Ладейного эндшпиля в этой партии так и не случилось: у белых остался конь, у чёрных — слон."),
    (NAKAMURA_SINDAROV, "Это не ладейный эндшпиль: у белых ещё есть конь, у чёрных — слон."),
    (NAKAMURA_SINDAROV, "В ладейных эндшпилях активный король обычно решает больше, чем лишняя пешка."),
    (NAKAMURA_SINDAROV, "На 18-м ходу Накамура выиграл пешку d5, но уже на 19-м ходу Синдаров отыграл её ходом Nxf2."),
    (NAKAMURA_SINDAROV, "На 26-м ходу Синдаров отдал коня за слона: 26...Nxg2 27.Kxg2."),
    (NAKAMURA_SINDAROV, "Белые так и не смогли получить материальный перевес."),
    (NAKAMURA_CARLSEN, "В размене на 21–23-м ходах белые выиграли ферзя и ладью за ферзя и коня."),
    (NAKAMURA_CARLSEN, "Белые выиграли ладью за коня и пешку."),
    (NAKAMURA_CARLSEN, "Долгое время белые играли с лишней пешкой."),
    (NAKAMURA_CARLSEN, "Накамура остался с лишней пешкой после 33.Rxd6+ и довёл партию до победы."),
    (NAKAMURA_CARLSEN, "Ферзи разменялись на 21-м ходу, а потом белый конь забрал ещё и ладью f8."),
    (SINDAROV_NAKAMURA, "Партия перешла в ферзевый эндшпиль и закончилась повторением ходов."),
    (SINDAROV_NAKAMURA, "Разменялись почти все фигуры, и партия закончилась повторением ходов."),
]


@pytest.mark.unit
@pytest.mark.parametrize("pgn,sentence,why", WRONG)
def test_a_wrong_story_is_cut_when_the_check_is_on(check_on, pgn, sentence, why):
    issues = check_sentence(sentence, _ctx(pgn))
    assert issues and any(why in i for i in issues), issues


@pytest.mark.unit
@pytest.mark.parametrize("pgn,sentence", RIGHT)
def test_a_true_story_passes(check_on, pgn, sentence):
    assert check_sentence(sentence, _ctx(pgn)) == []


@pytest.mark.unit
def test_in_shadow_the_story_is_recorded_and_not_cut(monkeypatch):
    monkeypatch.setattr(config, "COACH_LOADED_GAME_CHECK", "shadow")
    ctx = _ctx(NAKAMURA_CARLSEN)
    sentence = "В итоге белые выиграли ферзя и ладью за ферзя и слона."
    assert check_sentence(sentence, ctx) == []
    [(part, said, issues)] = ctx.db_shadow
    assert part == "loaded_game" and "game's facts" in issues[0]


@pytest.mark.unit
def test_a_present_list_of_pieces_is_no_lead(check_on):
    """Recorded answer (Carlsen – Nepomniachtchi): «у белых две проходные плюс ладья и конь» lists what White has."""
    ctx = _ctx(NAKAMURA_CARLSEN)
    assert story_issues("У белых две проходные плюс ладья и конь, и Карлсен сдался.",
                        "у белых две проходные плюс ладья и конь, и карлсен сдался.", ctx, True,
                        lambda part: acd._sides_named(part, ctx.master_game)) == []


@pytest.mark.unit
def test_with_an_extra_pawn_is_not_the_piece_that_moved(check_on):
    """«…забрал пешку d5 и остался с лишней пешкой»: «пешкой» after «с» is what the side has, not the mover of 18.Qxd5
    (the move check read it as a pawn move and cut the move as told wrong)."""
    issues = check_sentence("На 18-м ходу Накамура забрал пешку d5.", _ctx(NAKAMURA_SINDAROV))
    assert issues == []
    issues = check_sentence("На 18-м ходу Накамура забрал пешку d5 и остался с лишней пешкой.", _ctx(NAKAMURA_SINDAROV))
    assert all("at move 18 it went" not in i for i in issues) and any("held only 3 plies" in i for i in issues)


# ── arrows on the position the board shows ────────────────────────────────────────────────────────────────────────

def _arrows(*pairs):
    return {"type": "draw_arrows", "arrows": [{"from": a, "to": b, "brush": "green"} for a, b in pairs]}


@pytest.mark.unit
def test_an_arrow_for_a_past_move_is_not_drawn_on_the_final_position():
    """The live case: get_game_pgn put the game up, then [[arrows: f3e5]] for 6.Nxe5 went onto its final position."""
    load = {"type": "load_pgn", "pgn": SINDAROV_NAKAMURA}
    kept, dropped = prune_board_actions([load, _arrows(("f3", "e5"))], chess.STARTING_FEN)
    assert kept == [load]
    assert dropped == ["f3e5: it is the game's move 6.Nxe5, made on another position — the board shows the final "
                       "position"]


@pytest.mark.unit
def test_an_arrow_is_judged_on_the_position_it_lands_on():
    final = _final(SINDAROV_NAKAMURA).fen()
    # the last move, still traced on the board: 34...Kf7, the king stands on f7
    action, dropped = arrow_verdicts(_arrows(("g8", "f7")), final, SINDAROV_NAKAMURA)
    assert dropped == [] and action["arrows"][0]["from"] == "g8"
    # 30.Qxe3 — the queen stands on e3 again, but it went to h6 and back since: that arrow is another position's
    action, dropped = arrow_verdicts(_arrows(("d2", "e3")), final, SINDAROV_NAKAMURA)
    assert action == {} and "30.Qxe3" in dropped[0][1]
    # a line of play: the second arrow starts where the first brought a piece
    action, dropped = arrow_verdicts(_arrows(("e3", "f3"), ("f3", "e5")), final, SINDAROV_NAKAMURA)
    assert dropped == [] and len(action["arrows"]) == 2
    # with no game on the board an arrow from an empty square is a line of play, as before
    action, dropped = arrow_verdicts(_arrows(("f3", "e5")), final)
    assert dropped == [] and action["arrows"]
    # at the ply it was played the move is drawn
    game = chess.pgn.read_game(io.StringIO(SINDAROV_NAKAMURA))
    board = game.board()
    for move in list(game.mainline_moves())[:10]:
        board.push(move)
    action, dropped = arrow_verdicts(_arrows(("f3", "e5")), board.fen(), SINDAROV_NAKAMURA, 10)
    assert dropped == [] and action["arrows"]


@pytest.mark.unit
def test_navigate_moves_the_board_the_arrows_are_judged_on():
    game = chess.pgn.read_game(io.StringIO(SINDAROV_NAKAMURA))
    board = game.board()
    for move in list(game.mainline_moves())[:11]:
        board.push(move)  # after 6.Nxe5
    kept, dropped = prune_board_actions([{"type": "navigate", "direction": "prev"}, _arrows(("f3", "e5"))],
                                        board.fen(), SINDAROV_NAKAMURA, 11)
    assert dropped == [] and kept[-1]["arrows"]


@pytest.mark.unit
def test_the_voice_path_tells_the_model_why_an_arrow_was_not_drawn():
    from src.boards import new_board
    from src.tool_bridge import _prune_voice_arrows

    class _Session:
        def __init__(self, board):
            self.board_state = board.fen
            self._board = board

        def active_board(self):
            return self._board

    session = _Session(new_board("s1", pgn=SINDAROV_NAKAMURA))
    kept, dropped = _prune_voice_arrows([_arrows(("f3", "e5"), ("e3", "e7"))], session)
    assert kept[0]["arrows"] == [{"from": "e3", "to": "e7", "brush": "green"}]
    assert dropped and dropped[0].startswith("f3e5: it is the game's move 6.Nxe5")
    # a FEN alone (no session) keeps the old rule
    kept, dropped = _prune_voice_arrows([_arrows(("f3", "e5"))], session.board_state)
    assert dropped == [] and kept[0]["arrows"]


@pytest.mark.unit
def test_the_text_turn_judges_arrows_against_the_game_the_board_shows():
    from src.boards import new_board
    from src.server import _shown_game

    board = new_board("s1", pgn=SINDAROV_NAKAMURA)

    class _Session:
        board_state = board.fen

        def get_board(self, board_id):
            return board if board_id == board.id else None

        def active_board(self):
            return board

    assert _shown_game(_Session(), board.id) == (SINDAROV_NAKAMURA, 68)
    _Session.board_state = chess.STARTING_FEN  # the session moved on: no game to judge against
    assert _shown_game(_Session(), board.id) == (None, None)
