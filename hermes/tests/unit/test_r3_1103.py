"""R3 03.11: the rewrite proves the relation a sentence states; a cut leaves a whole answer (VERDICT 1102b §1b, §1c).

§1c: «Слон на f5 бьёт по c2, поэтому этот пункт и стоит укрепить — например, ходом Be2» (plan-caro-adv) was shown as
proven: Be2 is the engine's move and «f5 бьёт по c2» is true, but Be2 does not defend c2. The proof now asks the board
for the relation itself: the piece the named move moves must hold it, after the move, to the point the sentence is
about (src/rewrite_proof._means_holds), with the relation judge (claim_judge.judge_on).
§1b: 39 of 41 rewrites were abandoned; most first sentences were true and refused because no claim carried one of
their words. Classes proven now from the board: the castling rook's squares, the check on the board, «только» before
the one defender, a claim about the piece the engine's move puts there, an opening's name («берлинская защита»), the
idioms «только что» / «всё равно». And a cut no longer leaves «точнее, …», «Поэтому …», a doubled blank line or a
list that skips a number.
Every board here is new (a Caro-Kann advance, a Two Knights, a Scotch centre, a Scandinavian, a Danish-like centre
after …Qxe4+); both directions are tested on each.
"""
import pytest
import chess

from src.answer_check import CheckContext, check_sentence, strip_leaning_start
from src.rewrite_proof import anchors, mend_after_cut, normalized, prove, renumber_item

CARO = "rn1qkbnr/pp2pppp/2p5/3pPb2/3P4/8/PPP2PPP/RNBQKBNR w KQkq - 1 4"
TWO = "r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 5 4"
SCOT = "r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/8/PPP2PPP/RNBQKBNR w KQkq - 1 3"
SCANDI = "rnb1kbnr/ppp1pppp/8/3q4/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 3"
QXE4 = "rnb1kbnr/pppp1ppp/8/8/3pq3/2P2N2/PP3PPP/RNBQKB1R w KQkq - 0 5"  # White in check from e4
QXE4_NOC1 = "rnb1kbnr/pppp1ppp/8/8/3pq3/2P2N2/PP3PPP/RN1QKB1R w KQkq - 0 5"  # no bishop on c1: d1 defends b1 too
QXE4_BLOCKED = "rnb1kbnr/pppp1ppp/8/8/3pq3/2P2N2/PP2BPPP/RNBQK2R b KQkq - 1 5"  # Be2 blocked it: no check
ITAL_BE7 = "r1bqk1nr/ppppbppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
ITAL_QE7 = "r1b1kbnr/ppppqppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"


def _status(sentence, fen, line=None):
    ctx = CheckContext.from_fens([fen])
    if line:
        ctx.engine_lines = [line.split()]
    if check_sentence(sentence, ctx):
        return "cut"  # the check itself refuses it: never shown either
    return prove(sentence, ctx).status


def _shown(status):
    return status == "proven"


@pytest.mark.unit
class TestTheRelationOfTheMove:
    @pytest.mark.parametrize("fen, line, sentence, shown", [
        # the live gap (plan-caro-adv) and its new-board twin: the move named as the means does not defend the point
        (CARO, "Be2 e6", "Слон на f5 бьёт по c2, поэтому этот пункт и стоит укрепить — например, ходом Be2.", False),
        (TWO, "Be7 d3", "Слон c4 бьёт по f7, поэтому этот пункт стоит укрепить ходом Be7.", False),
        (CARO, "Bd3 Bxd3", "Слон f5 бьёт по c2, поэтому этот пункт стоит укрепить ходом Bd3.", True),
        (TWO, "Qe7 d3", "Слон c4 бьёт по f7, поэтому этот пункт можно укрепить ходом Qe7.", True),
        # no claim at all: the sentence's own square is the point
        (CARO, "Bd3 Bxd3", "Пункт c2 стоит защитить ходом Bd3.", True),
        (CARO, "Be2 e6", "Пункт c2 стоит защитить ходом Be2.", False),
        (SCOT, "Be3 exd4", "Пешку d4 можно подкрепить ходом Be3.", True),
        (SCOT, "Bd3 exd4", "Пешку d4 можно подкрепить ходом Bd3.", False),
        (SCOT, "Nf3 exd4", "Конь c6 нападает на d4, так что эту пешку стоит поддержать ходом Nf3.", True),
        (SCOT, "Nc3 exd4", "Конь c6 нападает на d4, так что эту пешку стоит поддержать ходом Nc3.", False),
        (SCOT, "c3 exd4", "Конь c6 нападает на d4, так что эту пешку стоит поддержать — 3.c3.", True),
        # an attack stated of the move
        (SCANDI, "Nc3 Qa5", "Сыграй Nc3, и конь будет угрожать ферзю d5.", True),
        (SCANDI, "Nf3 Bg4", "Сыграй Nf3, и конь будет угрожать ферзю d5.", False),
    ])
    def test_the_named_move_must_hold_the_relation(self, fen, line, sentence, shown):
        assert _shown(_status(sentence, fen, line)) is shown

    def test_the_strengthen_words_are_relation_words(self):
        kinds = {(a.kind, a.text) for a in anchors(normalized("Укрепи c2 ходом Bd3, поддерживая e5 и подкрепляя d4."))}
        assert {("relation", "Укрепи"), ("relation", "поддерживая"), ("relation", "подкрепляя")} <= kinds

    def test_no_move_named_proves_no_relation_of_a_move(self):
        assert _status("Пункт c2 стоит укрепить.", CARO, "Bd3 Bxd3") == "unproven"
        assert _status("Пункт c2 стоит укрепить ходом Bd3.", CARO, None) == "unproven"  # no engine line

    def test_the_centre_is_its_four_squares(self):
        assert _status("Играй d3, укрепляя центр.", "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 2",
                       "d3 Nc6") == "proven"  # d3 defends e4
        assert _status("Играй h3, укрепляя центр.", "rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 2",
                       "h3 Nc6") == "unproven"

    @pytest.mark.parametrize("fen, line, sentence, shown", [
        # live name-scandi's kind: «конь» unsquared, the knight the engine's move puts on c3
        (SCANDI, "Nc3 Qa5", "Лучший ход — Nc3: конь нападает на чёрного ферзя на d5.", True),
        (SCANDI, "Nf3 Bg4", "Лучший ход — Nf3: конь нападает на чёрного ферзя на d5.", False),
    ])
    def test_the_piece_the_engine_move_puts_there(self, fen, line, sentence, shown):
        assert _shown(_status(sentence, fen, line)) is shown


@pytest.mark.unit
class TestFalseRefusals:
    @pytest.mark.parametrize("fen, sentence, shown", [
        (QXE4, "Коня b1 прикрывает только ладья a1.", True),
        (QXE4_NOC1, "Коня b1 прикрывает только ладья a1.", False),  # the queen on d1 defends it too
        (ITAL_BE7, "Пешку f7 защищает только король.", True),
        (ITAL_QE7, "Пешку f7 защищает только король.", False),  # and the queen on e7
    ])
    def test_only_before_the_one_defender(self, fen, sentence, shown):
        assert _shown(_status(sentence, fen)) is shown

    def test_the_check_on_the_board(self):
        # live st3#10's kind: after 4...Qxe4+ «…а не сам шах» is the check on the board
        sentence = "Ферзь на e4 бьёт твоего коня b1 и коня f3 — вот главная опасность, а не сам шах."
        assert _status(sentence, QXE4) == "proven"
        assert _status("Ферзь на e4 бьёт коня f3 — вот главная опасность, а не шах.", QXE4_BLOCKED) == "unproven"
        # a check a move gives is the move's, not the board's
        assert _status("Ход Be2 даёт шах.", QXE4, "Be2 d3") in ("unproven", "cut")

    @pytest.mark.parametrize("sentence, status", [
        ("Движок ответил 4.O-O — король белых ушёл в безопасность, ладья встала на f1.", "proven"),  # live st2#4
        ("Белые ответили 4.O-O: рокировка сделана.", "proven"),
        ("Движок ответил 4.O-O — ладья встала на d1.", "unproven"),
    ])
    def test_the_castling_rook(self, sentence, status):
        moves = ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O"]
        board = chess.Board()
        for san in moves:
            board.push_san(san)
        ctx = CheckContext.from_fens([board.fen()])
        ctx.game_moves = list(moves)
        assert check_sentence(sentence, ctx) == []
        assert prove(sentence, ctx).status == status

    @pytest.mark.parametrize("sentence, status", [
        ("Это итальянская партия, венгерская защита.", "neutral"),
        ("Сицилианская защита здесь не при чём.", "neutral"),
        ("Это защита Филидора.", "neutral"),
        ("Пешку f7 защищает король — защита держится.", "unproven"),  # a defence, not a name
    ])
    def test_an_opening_name_is_no_relation(self, sentence, status):
        assert _status(sentence, ITAL_BE7) == status

    def test_idioms_are_no_quantifiers(self):
        text = normalized("Белые только что рокировались, и всё равно всё ещё лучше.")
        kinds = [(a.kind, a.text) for a in anchors(text)]
        assert ("quant", "только") not in kinds and ("eval", "равно") not in kinds
        assert ("quant", "все") not in kinds and ("quant", "всё") not in kinds
        assert ("quant", "только") in [(a.kind, a.text) for a in anchors(normalized("Его защищает только король."))]


@pytest.mark.unit
class TestWhatACutLeaves:
    @pytest.mark.parametrize("text, shown, want", [
        ("точнее, ферзь e4 атакует коня b1, и пешка e4 уже съедена.", "",
         "Ферзь e4 атакует коня b1, и пешка e4 уже съедена."),  # live st3#8
        ("Поэтому белые сначала рокируются.", "Хороший вопрос. ", "Белые сначала рокируются."),
        ("Кроме того, конь c6 защищает e5.", "Да. ", "Конь c6 защищает e5."),
        ("... и тогда слон уходит на b3 без потерь.", "Да. ", "Слон уходит на b3 без потерь."),
        ("So the bishop has to retreat now.", "Yes. ", "The bishop has to retreat now."),
        ("e4 — лучший ход здесь, он занимает центр.", "Да. ", "e4 — лучший ход здесь, он занимает центр."),
        ("Ход сильный.", "Да. ", "Ход сильный."),
        ("И мат.", "Да. ", "И мат."),  # too short to stand alone without it
    ])
    def test_the_first_words_after_a_cut(self, text, shown, want):
        assert mend_after_cut(text, shown) == want

    def test_the_lesson_tutor_repair_is_unchanged(self):
        # /learn and the game comment keep src/answer_check.strip_leaning_start as it was
        assert strip_leaning_start("Поэтому белые сначала рокируются.") == "Поэтому белые сначала рокируются."
        assert strip_leaning_start("Затем выводи короля к пешкам.") == "Выводи короля к пешкам."

    @pytest.mark.parametrize("text, shown, cut, want", [
        ("3. Играй d3.", "План:\n1. Рокируйся.\n", [], "2. Играй d3."),
        ("4. Потом Re1.", "План:\n1. Рокируйся.\n2. Играй d3.\n", [], "3. Потом Re1."),
        ("2. Играй d3.", "План:\n", ["1. Рокируйся."], "1. Играй d3."),
        ("3. Nf3 Nc6 4. Bb5", "1. e4 e5\n", [], "3. Nf3 Nc6 4. Bb5"),  # a move number, not an item
        ("2. Играй d3.", "План:\n1. Рокируйся.\n", [], "2. Играй d3."),
    ])
    def test_a_list_goes_on_as_it_is_shown(self, text, shown, cut, want):
        assert renumber_item(text, shown, cut) == want


@pytest.mark.unit
class TestTheSideOfThePoint:
    @pytest.mark.parametrize("sentence, shown", [
        # Nf3 hits the black pawn on e5: it attacks it, it cannot defend it
        ("Пешку e5 стоит защитить ходом Nf3.", False),
        ("Пешку e5 стоит атаковать ходом Nf3.", True),
        # Nc3 defends White's own pawn on e4, it cannot attack it
        ("Пешку e4 стоит защитить ходом Nc3.", True),
        ("Пешку e4 стоит атаковать ходом Nc3.", False),
    ])
    def test_defend_own_attack_other(self, sentence, shown):
        fen = "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
        line = "Nf3 Nc6" if "Nf3" in sentence else "Nc3 Nf6"
        assert _shown(_status(sentence, fen, line)) is shown


@pytest.mark.unit
class TestTheSideInCheck:
    @pytest.mark.parametrize("sentence, status", [
        ("Белые под шахом, и ферзь e4 бьёт коня b1.", "proven"),
        ("Чёрные под шахом, и ферзь e4 бьёт коня b1.", "unproven"),
        ("Ты под шахом, и ферзь e4 бьёт коня b1.", "proven"),  # the student plays White here
    ])
    def test_the_side_named_is_the_side_in_check(self, sentence, status):
        ctx = CheckContext.from_fens([QXE4], student_color=chess.WHITE)
        assert check_sentence(sentence, ctx) == []
        assert prove(sentence, ctx).status == status

    def test_i_am_not_in_check_when_you_are(self):
        ctx = CheckContext.from_fens([QXE4], student_color=chess.WHITE)  # the coach plays Black: not in check
        check_sentence("Я под шахом.", ctx)
        assert prove("Я под шахом.", ctx).words == ["шахом"]
        ctx = CheckContext.from_fens([QXE4], student_color=chess.BLACK)  # the coach plays White: in check
        check_sentence("Я под шахом.", ctx)
        assert prove("Я под шахом.", ctx).status == "proven"


# ── the turn: what the student sees after a cut ─────────────────────────────────────────────────────────────────
import json  # noqa: E402
from unittest.mock import MagicMock, patch  # noqa: E402

RUY = "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 2 5"
WRONG = "Слон a4 нападает на пешку f7."  # false on RUY: the bishop on a4 hits c6
UNPROVEN = "Конь вынужден уйти на g5 с шахом."  # the rewrite's first sentence: unproven, so it is abandoned


def _turn(draft, rewrite=UNPROVEN, fen=RUY, user="r3-user"):
    from fastapi.testclient import TestClient

    from src.quick_reply import QuickReply
    from src.server import app
    from src.user_profile import UserProfile

    agent = MagicMock()

    def _chat(msg, stream_callback=None):
        for part in draft:
            stream_callback(part)
        return "".join(draft)

    agent.chat.side_effect = _chat

    def _fix(**kwargs):
        for i in range(0, len(rewrite or ""), 7):
            kwargs["on_delta"](rewrite[i:i + 7])
        return QuickReply(model=kwargs["model"])

    client = TestClient(app)
    with patch("src.server.config.COACH_ENGINE_NOTE", False), \
            patch("src.server.config.COACH_OPENING_PRESTEP", False), \
            patch("src.server.config.COACH_ANSWER_FIX", True), \
            patch("src.quick_reply.stream_completion", side_effect=_fix), \
            patch("src.server._create_agent", return_value=agent), \
            patch("src.server.load_user_profile", return_value=UserProfile(user_id=user)):
        headers = {"X-User-Id": user}
        sid = client.post("/api/coach/sessions", headers=headers).json()["id"]
        resp = client.post("/api/coach/chat", headers=headers,
                           json={"message": "что тут происходит?", "session_id": sid, "fen": fen})
    frames = [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]
    return "".join(f.get("delta", "") for f in frames).strip()


@pytest.mark.unit
class TestTheTurnAfterACut:
    def test_a_leaning_word_after_the_cut_goes(self):
        text = _turn(["Хороший вопрос.\n", WRONG + "\n", "Поэтому спокойно рокируйся, а потом играй d3."])
        assert text == "Хороший вопрос.\nСпокойно рокируйся, а потом играй d3."

    def test_the_rest_of_a_split_sentence_opens_as_a_sentence(self):
        # live st3#8: «…c3... точнее, ферзь e4 атакует коня b1» — the gate splits at «...», the first part is cut
        text = _turn([WRONG[:-1] + "... точнее, конь f3 нападает на пешку e5."])
        assert text == "Конь f3 нападает на пешку e5."

    def test_a_list_goes_on_without_the_cut_item(self):
        text = _turn(["План:\n", "1. Рокируйся.\n", "2. " + WRONG + "\n", "3. Играй d3.\n", "4. Потом Re1."])
        assert text == "План:\n1. Рокируйся.\n2. Играй d3.\n3. Потом Re1."

    def test_a_paragraph_break_is_not_doubled(self):
        text = _turn(["Хороший вопрос.\n\n", WRONG + "\n\n", "Кроме того, конь f3 нападает на пешку e5."])
        assert text == "Хороший вопрос.\n\nКонь f3 нападает на пешку e5."

    def test_an_answer_with_no_cut_is_as_written(self):
        draft = ["План:\n", "1. Рокируйся.\n", "3. Играй d3.\n\n", "Поэтому не спеши: конь f3 нападает на пешку e5."]
        assert _turn(draft) == "".join(draft).strip()

    def test_a_proven_rewrite_still_stands_in(self):
        text = _turn(["Хороший вопрос. ", WRONG + " ", "Спокойно рокируйся."],
                     rewrite="Конь f3 нападает на пешку e5, а защищает её конь c6.")
        assert text == "Хороший вопрос. Конь f3 нападает на пешку e5, а защищает её конь c6."


@pytest.mark.unit
def test_castling_told_of_its_side():
    moves = ["e4", "e5", "Nf3", "Nc6", "Bb5", "Nf6", "O-O"]
    board = chess.Board()
    for san in moves:
        board.push_san(san)
    for sentence, status in [("Белые ответили 4.O-O: короткая рокировка сделана.", "proven"),
                             ("Белые ответили 4.O-O: длинная рокировка сделана.", "unproven")]:
        ctx = CheckContext.from_fens([board.fen()])
        ctx.game_moves = list(moves)
        check_sentence(sentence, ctx)
        assert prove(sentence, ctx).status == status, sentence
