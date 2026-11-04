"""fix1103: what review-fp and review-miss (03.11, on next-1031 0af5b5f0) found, closed by class — on new boards.

HEAD-only false cuts and regressions:
- a verb of taking with no material object («Забирай центр ходом d4», «Выигрывай темп ходом e5», "Grab space with
  e5") is no capture: the written move (a bare pawn move too) is played, or the claim is left alone; "Just/Simply
  take …" heads a clause, and a «сейчас»/"now" right after the move says when to make it (src/material_frames);
- a block claim is not judged on the check a later move of the same sentence gives after the blocking piece moved
  («Закрыться конём тоже не помогает: на Nc6 последует Qxc6+»);
- «После <ход> единственный ход — X» where the move is in the middle of the line the sentence before wrote: that line
  is a reading too (src/answer_check_rules.line_walk / _readings);
- a named line's outcome told in any words for the side to move goes to the engine again («Вариант Ng5 d5 exd5 Nxd5 —
  у белых хорошая атака»); a side or a piece of the other colour named there keeps it out;
- «Bb5+ — с шахом» describes the move: no proposal;
- mend_after_cut keeps fixed phrases («So far», «Тогда как», «И X, и Y», «а-пешка»); a candidate-move list is
  renumbered after a cut item.
Shared false cuts: a later step of a plan («а потом сыграй e6», «потом можно … Nc6») is no move of the board now; a
joined verb that is no attack ends the targets («бьёт пешку и подставляет ферзя d1 под слона g4»); "checks the king
on e8 and hits …" has the knight as its subject; a SAN repeating the last game move is also the reply now; a bare
«ферзь» in a defender list that took the other side's queen's square says nothing.
Misses (src/answer_check_more): checks told in words, where a piece can go, a move told to be played now, «силы
равны», trades on a line, plans' preconditions, a written line's impossible move; «примерно равный» is no longer a
piece for a pawn or the exchange; past and win-back outcome verbs in line verdicts.
"""
from __future__ import annotations

import chess
import pytest

from src.answer_check import CheckContext, check_sentence, proposed_move


def _ctx(moves: str, color):
    if "/" in moves:
        fen = chess.Board(moves).fen()
    else:
        b = chess.Board()
        for m in moves.split():
            b.push_san(m)
        fen = b.fen()
    return CheckContext.from_fens([fen], student_color=None if color is None else color == "w")


CASES = [
    ('told', '4kn-idiom-cap', 'e4 e5 Nf3 Nc6 Nc3 Nf6 d4 exd4', None, [['Забирай центр ходом Nxd4, и материал снова равный.', 0]]),
    ('told', '4kn-idiom-quiet-true', 'e4 e5 Nf3 Nc6 Nc3 Nf6 d4 exd4', None, [['Выигрывай темп ходом h3, и у чёрных останется лишняя пешка.', 0]]),
    ('told', '4kn-idiom-pawn-true', 'e4 e5 Nf3 Nc6 Nc3 Nf6 d4 exd4', None, [['Захватывай пространство ходом e5, и у чёрных по-прежнему лишняя пешка.', 0]]),
    ('told', '4kn-take-true', 'e4 e5 Nf3 Nc6 Nc3 Nf6 d4 exd4', None, [['Бери пешку d4 конём, и материал снова равный.', 0]]),
    ('told', 'caro-en-just', 'e4 c6 d4 d5 exd5', 'b', [['Just recapture on d5 and the material is equal again.', 0]]),
    ('told', 'caro-en-simply-now', 'e4 c6 d4 d5 exd5', 'b', [['Simply take on d5 now, and material is level.', 0]]),
    ('told', 'caro-en-now-claim', 'e4 c6 d4 d5 exd5', 'b', [['Recapture soon — right now White is a pawn up.', 0]]),
    ('told', 'qgd-ru-now-move', 'd4 d5 c4 e6 Nc3 Nf6 cxd5', 'b', [['Возьми сейчас на d5 пешкой, и материал опять равный.', 0]]),
    ('told', 'qgd-ru-now-claim', 'd4 d5 c4 e6 Nc3 Nf6 cxd5', 'b', [['Возьми на d5 конём — сейчас у белых лишняя пешка.', 0]]),
    ('told', 'petroff-take-true', 'e4 e5 Nf3 Nf6 Nxe5 d6 Nf3', 'b', [['Бери пешку e4 конём, и материал снова равный.', 0]]),
    ('told', 'petroff-take-false', 'e4 e5 Nf3 Nf6 Nxe5 d6 Nf3', 'b', [['Бери пешку e4 конём — и у белых всё ещё лишняя пешка.', 1]]),
    ('told', 'petroff-plain-now', 'e4 e5 Nf3 Nf6 Nxe5 d6 Nf3', 'b', [['Материал равный.', 1]]),
    ('block', 'qga-a02', 'd4 d5 c4 dxc4 e3 b5 a4 c6 axb5 cxb5 Qf3', None, [['Закрыться конём тоже не помогает: на Nc6 последует Qxc6+.', 0]]),
    ('block', 'sicil-new1', 'e4 c5 Nf3 d6 Bb5+', None, [['Закрыться конём можно: Nc6 или Nd7.', 0], ['Закрыться ладьёй нельзя — её нет рядом.', None]]),
    ('block', 'sicil-new3', 'e4 c5 Nf3 d6 Bb5+', None, [['Закрыться слоном тоже не спасает: на Bd7 последует Bxd7+.', 0]]),
    ('block', 'sicil-new3-false', 'e4 c5 Nf3 d6 Bb5+', None, [['Закрыться ферзём можно: Qa5 тут же закрывает.', 1]]),
    ('block', 'frch-new', 'e4 e6 d4 d5 Nc3 Bb4 e5 c5 a3 Bxc3+', None, [['Закрыться пешкой здесь можно: bxc3.', None], ['Закрыться ферзём — Qd2 — тоже можно.', 0], ['Закрыться конём нельзя: на Ne2 последует Bxe2? Нет, слон на c3 — ход Ne2 просто разрешён.', None]]),
    ('reach', 'qgd', 'd4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7', None, [['Слон g5 может отступить на h4.', 0], ['Слон g5 может отступить на e3.', 1], ['Слон g5 может отступить на c1.', 1], ['Слон g5 может отступить на f4 или h4.', 0], ['Конь c3 может отступить на b1.', 0], ['Конь f6 может отступить на e8.', 0], ['Конь f6 может отступить на h7.', 1], ['Ферзь d8 может отступить на e8.', 0], ['Слон e7 может отступить на f8.', 1], ['Если белые сыграют Bxf6, слон e7 может отступить на d6.', None], ['Слон g5 не может отступить на e3.', 0], ['The bishop on g5 can retreat to e3.', 1], ['The knight on c3 can go back to b1.', 0], ['Конь может отступить на e8.', 0], ['Ладья f8 может уйти на e8.', 0], ['Ладья a1 может перейти на c1.', 0], ['Ладья a1 может перейти на d1.', 1], ['Король g8 может уйти на h8.', 0]]),
    ('reach', 'pin', 'e4 e5 Nf3 Nc6 Bb5 Nf6 Nc3 d6', None, [['Конь c6 может отступить на e7.', 1], ['Конь c6 может уйти на b8.', 1], ['Конь f6 может отступить на g8.', 0], ['Чёрный конь может отступить на g8.', None], ['Слон b5 может отступить на a4 или e2.', 0], ['Слон b5 может отступить на f1.', 0], ['Слон b5 может отступить на d7.', 1], ['Слон c8 может уйти на f5.', 0]]),
    ('reach', 'game', 'e4 e5 Nf3 Nc6 Bb5 Nf6 Nc3 d6', 'w', [['Твой слон b5 может отступить на c4.', 0], ['Твой слон может отступить на d3.', 0], ['Твой ферзь может уйти на d3.', 1], ['Твой конь f3 может отступить на g1.', 0]]),
    ('chk', 'ruy', 'e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O', None, [['Ход Bxf7 даёт шах королю g8.', 0], ['Ход Bd5 даёт шах.', 1], ['Qb3 — с шахом.', None], ['Ход Ng5 — это шах.', 1], ['Bxf7 — с шахом, но слишком рано.', 0], ['Ход Bd5 не даёт шаха.', 0], ['Если бы пешки f7 не было, Bd5 дал бы шах.', 0], ['Bd5 gives check.', 1], ['Bxf7 is check.', 0], ['После h3 Bd5 — шах?', None]]),
    ('chk', 'sicil', 'e4 c5 Nf3 d6 d4 cxd4 Nxd4 Nf6 Nc3 a6', None, [['Ход Nd5 даёт шах.', 1], ['Bb5 — с шахом.', 0], ['Ход Bb5 даёт шах королю e8.', 0], ['Qa4 — шах королю.', 0], ['Ndb5 — шах.', 1], ['Ход Bc4 даёт шах.', 1]]),
    ('chk', 'endg', '8/8/3k4/8/3PK3/8/8/R7 w - - 0 1', None, [['Ход Ra6 даёт шах.', 0], ['Ra7 — с шахом.', 1], ['Ход Ra6+ даёт шах.', 0], ['Ход Rd1 даёт шах.', 1]]),
    ('chk2', 'grun', 'd4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Nf3 c5 Be3 Qa5 Qd2 O-O Rc1 cxd4 cxd4 Qxd2+ Kxd2', None, [['Ход ...Bh6 идёт с шахом.', 1], ['Ход ...Bxd4 идёт с шахом.', 1], ['...Rd8 — с шахом.', 1]]),
    ('chk2', 'k4', 'e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6 d4 exd4 cxd4 Bb4+', None, [['Ход Bd2 закрывает от шаха.', 0], ['Ход Nc3 — тоже защита от шаха.', 0], ['Bd2 — блок, без шаха.', 0]]),
    ('illeg2', 'caro', 'e4 c6 d4 d5 Nc3 dxe4 Nxe4 Bf5 Ng3 Bg6 h4 h6 Nf3 Nd7', None, [['Сыграй Bd3.', 0], ['Играй Bc4 — развитие.', 0], ['Сыграй Qd3?', 0], ['Сыграй Rh3.', 0], ['Сыграй Ne5, а потом Nxd7.', 0], ['Лучший ход здесь — Qxd7+.', 1], ['Тогда сыграй Qxd7+.', None], ['Не играй Qxd7+.', 0], ['Лучшим ходом было бы Qxd7+.', None], ['Play Qxd7+ now.', 1], ['Play Bd3 and castle.', 0], ['Castle short: O-O.', 1]]),
    ('illeg2', 'ruyb', 'e4 e5 Nf3 Nc6 Bb5', 'b', [['Сыграй Nge7.', 0], ['Играй Bb4.', 0], ['Играй Bc5 и Bxf2+ потом.', 0], ['Сыграй Qh4, нападая на e4.', 0], ['Сыграй Qd6 сейчас.', 1], ['Сыграй a6, спрашивая слона.', 0], ['Рокируйся в короткую — O-O.', 1]]),
    ('illeg2', 'ruyw', 'e4 e5 Nf3 Nc6 Bb5', 'w', [['Сыграй Bxc6.', 0], ['Играй Bb4.', 0]]),
    ('illeg3', 'noq', 'd4 Nf6 c4 g6 Nc3 d5 cxd5 Nxd5 e4 Nxc3 bxc3 Bg7 Nf3 c5 Be3 Qa5 Qd2 O-O Rc1 cxd4 cxd4 Qxd2+ Kxd2', None, [['Лучший ход здесь — ...Qd8, ферзь возвращается в центр.', 1], ['Сыграй ...Rd8+ — шах королю на d2.', 1], ['Сыграй ...Rd8 — шах королю.', 1], ['Лучший ход — ...Nc6.', 0], ['Сыграй ...Bxd4.', 0]]),
    ('illeg3', 'noq2', 'e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4 Qxd4 Qf6 Qxf6 Nxf6', None, [['Лучший ход — Qe2.', 1], ['Сыграй Nc3.', 0], ['Сыграй Bc4+.', 1], ['Играй Bb5+, это шах.', 1]]),
    ('forces', 'qvr', '6k1/5ppp/8/8/8/8/1r3PPP/Q5K1 w - - 0 31', None, [['Силы равны.', 0], ['Силы примерно равны.', 0], ['Соотношение сил равное.', 0]]),
    ('forces', 'rook-down', 'r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/3P1N2/PPP2PPP/RNBQK3 w Qkq - 0 6', None, [['Силы примерно равны, так что играй спокойно.', 1], ['Соотношение сил равное.', 1], ['По силам примерно паритет.', 1], ['Силы не равны: у чёрных лишняя ладья.', 0], ['Если бы ладья была на h1, силы были бы равны.', 0], ['The forces are equal.', 1]]),
    ('forces', 'eq', 'e4 e5 Nf3 Nc6 Bc4 Bc5', None, [['Силы равны.', 0], ['Силы примерно равны.', 0], ['У сторон равные силы.', 0]]),
    ('forces', 'gambit', 'e4 e5 f4 exf4', None, [['Силы примерно равны: пешка отдана за развитие.', 0]]),
    ('apx', 'n-for-p', 'r1bqkb1r/pppppppp/2n5/8/8/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4', None, [['Материал примерно равный.', 1], ['По материалу почти поровну.', 1], ['Материал практически равный.', 1]]),
    ('apx', 'exch', '6k1/5ppp/8/8/8/1B6/5PPP/2r3K1 w - - 0 30', None, [['Материал примерно равный.', 1], ['Здесь примерно равенство по материалу.', 1]]),
    ('apx', 'one-pawn', 'e4 d5 exd5 Nf6', None, [['Материал примерно равный.', 0], ['Позиция близка к равной по материалу.', 0], ['Материал равный.', 1]]),
    ('apx', 'two-pawns', 'rnbqkbnr/ppp2ppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 3', None, [['По материалу почти поровну.', 0]]),
    ('apx', 'r-vs-bp', '6k1/5ppp/8/8/8/1b6/5PP1/2R3K1 w - - 0 30', None, [['Материал примерно равный.', 0]]),
    ('trade', 'it', 'e4 e5 Nf3 Nc6 Bc4 Nf6 d3 Be7 O-O O-O Re1 d6 c3 Na5', None, [['Размен Bxf7+ Rxf7 — слон за пешку.', 0], ['Размен Bxf7+ Rxf7 — это равный обмен.', 1], ['Bxf7+ Rxf7 — слон за пешку, материал не в твою пользу.', 0]]),
    ('trade', 'sc', 'e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nf6 Nxc6 dxc6', None, [['Размен Qxd8+ Kxd8 — это обмен ферзей, материал остаётся равным.', 0], ['Qxd8+ Kxd8 — ферзь за ферзя.', 0], ['Размен Qxd8+ Kxd8 — ферзь за слона.', 1]]),
    ('trade', 'q', 'e4 d5 exd5 Qxd5 Nc3 Qa5 d4 Nf6 Nf3 Bf5 Ne5 e6 g4 Bg6 h4 Bb4 Bd2 Nbd7', None, [['Nxg6 — это размен коня на слона.', 0], ['Размен Nxd7 Nxd7 — обмен коней.', 0], ['Размен Nxd7 Nxd7 — равный обмен.', 0], ['Размен Nxd7 Nxd7 — конь за пешку.', 1]]),
    ('trade', 'hang', 'e4 e5 Nf3 d6 Bc4 Bg4 Nc3 g6 Nxe5 Bxd1', None, [['Bxf7+ — это размен слона на пешку.', 1]]),
    ('trade', 'noreply', 'r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 0 4', None, [['Bxc6 — это размен слона на коня.', 0], ['Nxe5 — это размен коня на пешку.', 0]]),
    ('trade', 'q2', 'r1bqkbnr/pppp1ppp/2n5/4p3/3PP3/5N2/PPP2PPP/RNBQKB1R b KQkq - 0 3', None, [['Размен exd4 Nxd4 — пешка за пешку, равный обмен.', 0], ['Размен Nxd4 Nxd4 exd4 — конь за коня.', 1]]),
    ('plan', 'kd2', 'd4 d5 c4 e6 Nc3 Nf6 cxd5 exd5 Bg5 c6 e3 Bf5 Qf3 Bg6 Bxf6 Qxf6 Qxf6 gxf6 Kd2', 'w', [['Твой план — длинная рокировка и атака.', 1], ['План белых — рокировка в короткую сторону.', 1], ['План — Kc2 и игра на ферзевом фланге.', 0], ['План чёрных — длинная рокировка.', 0], ['План чёрных — короткая рокировка и f6-f5.', 0], ['План белых — меньшинственная атака b2-b4-b5.', 0], ['План белых — прорыв e3-e4.', 0], ['План чёрных — прорыв c6-c5.', 0], ['План чёрных — прорыв e6-e5.', 1], ['План — использовать полуоткрытую линию c.', 0], ['План чёрных — давить по полуоткрытой линии g.', 0], ['План белых — использовать пешечное большинство на ферзевом фланге.', 1], ['План чёрных — использовать пешечное большинство на ферзевом фланге.', 0], ['План чёрных — использовать пешечное большинство на королевском фланге.', 1], ['План — ладьи на открытую линию e.', 1], ['Если бы король стоял на e1, план — длинная рокировка.', 0], ['Рокировки у белых уже не будет: король на d2.', 0]]),
    ('plan', 'open', 'e4 e5 Nf3 Nc6 d4 exd4 Nxd4 Nxd4 Qxd4 d6', None, [['План — ладья на открытую линию e.', 1], ['План белых — использовать полуоткрытую линию d.', 0], ['План белых — длинная рокировка и f4-f5.', 0], ['План чёрных — Be7, O-O и f7-f5.', 0], ['План белых — c-пешку на c4.', 0], ['План чёрных — d-пешкой d6-d5.', 0], ['План чёрных — e-пешкой вперёд.', 1], ['План белых — использовать большинство на ферзевом фланге.', 1]]),
    ('lines', 'qgd', 'd4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7', None, [['Продолжение Bxf6 Nxf6 Qxc7 — белые выигрывают пешку.', 1], ['Продолжение Bxf6 Nxf6 Qc2 — белые стоят лучше.', 0], ['Вариант cxd5 exd5 Bd3 c6 Qc2 — главная линия.', 0], ['Линия cxd5 Nxd5 Bxe7 Qxe7 Nxd5 exd5 — размены.', 0], ['После cxd5 exd5 Bd3 Re8 белые рокируются.', 0], ['Линия cxd5 exd5 Bxd5 — белые выигрывают пешку.', 1], ['После Bd3 dxc4 Bxc4 c5 — нормальная игра.', 0]]),
    ('lines', 'blk', 'e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7', None, [['Вариант Bxc6 dxc6 Nxe5 Qd4 — чёрные отыгрывают пешку.', 0], ['Вариант Bxc6 bxc6 Nxe5 Qd4 Nf3 Qxe4 — пешка возвращена.', 1], ['Линия Bxc6 dxc6 Nxe5 Nxe4 Qe2 Qd4 — всё по теории.', 0], ['Линия Bxc6 dxc6 Nxe5 Qxd2+ — чёрные забирают пешку.', 1], ['Линия Bxc6 dxc6 Nxe5 Qxd2 — чёрные забирают пешку.', 0]]),
    ('lines2', 'alt', 'e4 e5 Nf3 Nc6', None, [['Отсюда и популярные продолжения — c4, d3, b3 или Bc4: каждое борется за центр.', 0], ['Продолжения Bb5 a6 или Bc4 Bc5 — обе главные.', 0], ['Линия Bb5 a6 Ba4 Nf6 O-O — испанская партия.', 0], ['Линия Bb5 a6 Bc4 Nf6 — слон уходит.', 0], ['Линия Bb5 a6 Ba4 Nf6 Bxe5 — неудачно.', 1]]),
    ('subj', 'a05', 'rn1qkbnr/ppp2p1p/3p2p1/4p3/2B1P1b1/2N2N2/PPPP1PPP/R1BQK2R w KQkq - 0 5', None, [['Сильнее всего здесь Nxe5: конь бьёт пешку и подставляет ферзя d1 под слона g4 — но это ловушка для чёрных.', 0]]),
    ('subj', 'new-ru', 'r1bqkb1r/pppp1ppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4', None, [['Ng5 — конь нападает на f7 и открывает ферзю d1 линию на h5.', 0], ['Конь f3 бьёт e5 и защищает пешку d4.', 1], ['Конь f3 атакует e5 и заодно нападает на h7.', 1], ['Конь f3 атакует e5 и отдаёт пешку e4.', 0]]),
    ('subj', 'new-en', '4k3/8/8/1r6/8/8/8/2N1K3 w - - 0 1', None, [['Na2 is no fork: the knight attacks the rook on b4? no.', None], ['The knight checks nothing here and hits the rook on b5 from d4 only.', None], ['Nd3 attacks the rook on b4 and covers e1.', None], ['After Nb3 the knight eyes the rook on b5 and defends d2.', None], ['The knight on c1 attacks the rook on b5.', 1], ['The rook on b5 attacks the knight on c1.', 1]]),
    ('subj', 'b14', 'r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1', None, [['Nc7+ is a fork: the knight checks the king on e8 and hits the rook on a8.', 0], ['The knight on d5 attacks the rook on a8.', 1]]),
    ('neg1', 'corp1', '6k1/5ppp/8/8/8/8/5PPP/3QR1K1 w - - 0 1', None, [['Решение такое: сначала ладья идёт на e8 с шахом — король вынужден уйти на g8, а там ферзь бьёт на h8 и ставит мат.', 0], ['Ферзь приходит на d8 с шахом.', None], ['Ход ферзём на d8 — это шах.', None]]),
    ('neg1', 'eleph', 'd4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5', None, [['После Nxd5 его бьёт конь f6, и защитить коня нечем: f6–d5 В итоге ты отдаёшь коня за пешку.', 0], ['Nxd5 Nxd5 Bxd8 — и ты отдаёшь слона за ферзя? Нет.', None], ['Nxd5 Nxd5 — конь за пешку.', 0], ['Nxd5 Nxd5 — конь за коня.', 1]]),
    ('struct', 'qgd', 'd4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7', None, [['После Bxf6 Bxf6 у чёрных сдвоенные пешки.', 1], ['После Bxf6 gxf6 у чёрных сдвоенные пешки на вертикали f.', 0], ['После Bxf6 Nxf6 у чёрных появятся сдвоенные пешки.', 1], ['После cxd5 exd5 у белых изолированная пешка d4.', 1], ['После cxd5 exd5 у чёрных изолированная пешка d5.', 1], ['После cxd5 Nxd5 у белых сдвоенные пешки.', 1], ['После размена на f6 у чёрных сдвоенные пешки.', None], ['Если после Bxf6 Bxf6, у чёрных не будет сдвоенных пешек.', 0]]),
    ('struct', 'iqp', 'e4 e6 d4 d5 Nd2 c5 exd5 exd5 Ngf3 Nc6 Bb5 Bd6 dxc5 Bxc5', None, [['После O-O Nge7 у чёрных изолированная пешка d5.', 0], ['После O-O Nge7 у белых изолированная пешка.', 1]]),
    ('matw', 'qvr', '6k1/5ppp/8/8/8/8/1r3PPP/Q5K1 w - - 0 31', None, [['По материалу всё ровно.', 1], ['Материал ровный.', 1], ['У белых три пешки.', 0], ['У белых четыре пешки.', 1], ['У каждой стороны по три пешки.', 0], ['У каждой стороны по четыре пешки.', 1], ['Ферзь стоит ровно на a1.', 0], ['Ровно через ход ферзь даст шах.', 0]]),
    ('matw', 'eq', 'e4 e5 Nf3 Nc6 Bc4 Bc5', None, [['По материалу всё ровно.', 0], ['У тебя столько же материала, сколько у соперника.', 0], ['Материал ровный, игра впереди.', 0], ['У белых восемь пешек.', 0], ['У чёрных семь пешек.', 1], ['Если белые возьмут на e5, у чёрных будет семь пешек.', 0]]),
    ('matw', 'exch', '6k1/5ppp/8/8/8/1B6/5PPP/2r3K1 w - - 0 30', 'w', [['У тебя примерно столько же материала, сколько у соперника.', 1], ['У тебя столько же пешек, сколько у соперника.', 0]]),
    ('minor', 'noQ', 'r1b2rk1/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w - - 0 8', None, [['У чёрных лишняя лёгкая фигура.', 1], ['У белых лишняя лёгкая фигура.', 1], ['Если бы конь не ушёл, у белых была бы лишняя лёгкая фигура.', 0]]),
    ('minor', 'minor', 'r1bqkb1r/pppp1ppp/2n5/8/8/5N2/PPPP1PPP/RNBQKB1R w KQkq - 0 4', None, [['У белых лишняя лёгкая фигура.', 0], ['У чёрных лишняя лёгкая фигура.', 1]]),
]


def _flat():
    for f, name, moves, color, seq in CASES:
        yield pytest.param(moves, color, seq, id=f"{f}-{name}")


@pytest.mark.parametrize("moves,color,seq", list(_flat()))
def test_sentences_on_new_boards(moves, color, seq):
    """Each case's sentences in order on one context: 1 must be flagged, 0 must pass (None: either)."""
    ctx = _ctx(moves, color)
    wrong = []
    for sentence, expect in seq:
        issues = check_sentence(sentence, ctx)
        if expect is not None and bool(issues) != bool(expect):
            wrong.append((sentence, issues))
    assert not wrong, wrong


ITAL = "e4 e5 Nf3 Nc6 Bc4 Bc5 c3 Nf6"


@pytest.mark.parametrize("sentence,san", [
    ("Вариант Ng5 d5 exd5 Nxd5 — у белых хорошая атака.", "Ng5"),
    ("Продолжение Bxf7+ Kxf7 Ng5+ — позиция белых лучше.", "Bxf7+"),
    ("Продолжение d4 exd4 cxd4 Bb4+ — белые отыгрывают пешку и стоят лучше.", "d4"),
    ("Вариант Ng5 d5 exd5 Na5 — и чёрный конь a5 забирает слона.", None),
    ("Линия d4 exd4 cxd4 Bb4+ — у чёрных хорошая игра.", None),
    ("Вариант Ng5 O-O Nxf7 Rxf7 — ладья f7 забирает коня.", None),
    ("Bb5+ — с шахом.", None),
])
def test_named_line_outcome_goes_to_the_engine(sentence, san):
    ctx = _ctx(ITAL, None)
    check_sentence(sentence, ctx)
    found = proposed_move(sentence, ctx)
    assert (found[2] if found else None) == san


@pytest.mark.parametrize("sentence,proposed", [
    ("Укрепи пункт b7 ходом Qd7, а потом сыграй e6 и разовьёшь слона f8.", False),
    ("Сыграй Nc3, а потом Be2.", True),
    ("Пешку e5 потом можно укрепить ходом Nc6.", False),
])
def test_a_later_step_of_a_plan_is_no_move_now(sentence, proposed):
    ctx = _ctx("r2qkb1r/pp2pppp/2n2n2/3p4/3P1Bb1/1QPB4/PP3PPP/RN2K1NR b KQkq - 4 7" if "b7" in sentence or "e5" in sentence
               else "rnbqkb1r/pp2pppp/3p1n2/8/3NP3/8/PPP2PPP/RNBQKB1R w KQkq - 1 5", None)
    found = proposed_move(sentence, ctx)
    assert (found is not None and found[2] in ("Nc3", "Be2")) == proposed  # never the later step (e6, Nc6, Be2 after Nc3)
    assert found is None or found[2] not in ("e6", "Nc6")


def test_forced_reply_in_the_middle_of_the_line_before_is_a_reading():
    from src.answer_check_rules import forced_reply_claim

    ctx = _ctx("d4 d5 c4 e6 Nc3 Nf6 Bg5 Nbd7 cxd5 exd5 Nxd5", None)
    check_sentence("Продолжение Nxd5 Bxd8 Bb4+ Qd2 Bxd2+ Kxd2 Kxd8 оставляет чёрных с лишней фигурой за пешку.", ctx)
    s = "После Bb4+ у белых единственный ход — Qd2."
    check_sentence(s, ctx)
    claim = ctx.forced_claims.get(s)
    assert claim is not None
    boards = [claim["board"]] + [c["board"] for c in claim["also"]]
    # the line's board: after Nxd5 Bxd8 Bb4+ — the d8 queen gone, Qd2 the only reply
    assert any(b.piece_at(chess.D8) is not None and b.piece_at(chess.D8).piece_type == chess.BISHOP for b in boards)


def test_forced_reply_alone_stays_on_the_board_now():
    ctx = _ctx("e4 e5 Nf3 Nc6 Bc4 Nd4 Nxe5", None)
    s = "После Qg5 у белых единственный ход — Nxf7."
    check_sentence(s, ctx)
    claim = ctx.forced_claims.get(s)
    assert claim is not None and not claim["also"]


@pytest.mark.parametrize("text,shown", [
    ("Thus far White has kept the extra pawn.", "Thus far White has kept the extra pawn."),
    ("So long as the e4 pawn stays loose, d3 is natural.", "So long as the e4 pawn stays loose, d3 is natural."),
    ("Тогда как у чёрных всё в порядке с развитием.", "Тогда как у чёрных всё в порядке с развитием."),
    ("А-пешка у белых проходная и быстрая.", "А-пешка у белых проходная и быстрая."),
    ("Ведь и конь, и слон уже развиты.", "И конь, и слон уже развиты."),
    ("И пешка f7, и пешка d7 атакованы конём e5.", "И пешка f7, и пешка d7 атакованы конём e5."),
    ("Поэтому конь f3 должен уйти отсюда.", "Конь f3 должен уйти отсюда."),
    ("So the knight on f6 is pinned to the queen.", "The knight on f6 is pinned to the queen."),
    ("Точнее, ферзь e4 атакует коня b1 и пешку b7.", "Ферзь e4 атакует коня b1 и пешку b7."),
])
def test_mend_after_cut_keeps_fixed_phrases(text, shown):
    from src.rewrite_proof import mend_after_cut

    assert mend_after_cut(text, "Prev.") == shown


def test_a_candidate_move_list_is_renumbered_after_a_cut_item():
    from src.rewrite_proof import renumber_item

    board = chess.Board("r1bqkb1r/ppp2ppp/2p2n2/8/4P3/8/PPPP1PPP/RNBQKB1R w KQkq - 0 5")
    shown = "Есть три хода:\n1. d3 — укрепляет пешку e4.\n"
    assert renumber_item("3. Nc3 — конь защищает e4.", shown, ["2. Qe2 — ферзь"], board=board).startswith("2. Nc3")
    # a game's move numbers (not every move legal on the board) stay as written
    game = chess.Board("rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    assert renumber_item("3. Nc3 — развитие.", "1. e4 — центр.\n", ["2. Nf3 — развитие."], board=game).startswith("3.")
    assert renumber_item("3. Nc3 — конь.", shown, ["2. Qe2 — ферзь"]).startswith("3.")  # no board: as written


def test_same_san_as_the_last_game_move_is_also_the_reply_now():
    moves = "e4 e5 Nf3 Nc6 Bb5 a6 Ba4 Nf6 O-O Be7 Re1 b5 Bb3 d6 c3 O-O h3 Na5 Bc2 c5 d4 Qc7 dxc5"
    b = chess.Board()
    for mv in moves.split():
        b.push_san(mv)
    ctx = CheckContext.from_fens([b.fen()])
    ctx.add_line(moves)
    ctx.game_moves = moves.split()
    ctx.student_color = chess.BLACK
    assert check_sentence("После dxc5 пешку e5 будет защищать ферзь c7 по диагонали.", ctx) == []
    assert check_sentence("После dxc5 пешку e5 защищает ферзь d8.", ctx)


def test_a_bare_queen_in_a_defender_list_is_not_the_other_sides():
    moves = "d4 Nf6 c4 e6 Nc3 Bb4 e3 O-O Bd3 d5 Nf3 c5 O-O dxc4 Bxc4"
    b = chess.Board()
    for mv in moves.split():
        b.push_san(mv)
    for spoken in (False, True):
        ctx = CheckContext.from_fens([b.fen()])
        ctx.add_line(moves)
        ctx.game_moves = moves.split()
        ctx.student_color = chess.WHITE
        assert check_sentence("Пешку d4 атакуют пешка c5 и ферзь d8, а защищают ферзь, конь f3 и пешка e3.", ctx,
                              spoken=spoken) == []
    ctx = CheckContext.from_fens([b.fen()])
    ctx.add_line(moves)
    ctx.game_moves = moves.split()
    ctx.student_color = chess.WHITE
    assert check_sentence("Пешку d4 защищает ферзь d8.", ctx)  # the queen's square written: still judged


def test_the_lesson_tutor_reads_none_of_the_new_claims():
    ctx = _ctx("d4 d5 c4 e6 Nc3 Nf6 Bg5 Be7 e3 O-O Nf3 Nbd7", None)
    ctx.relation_surface = "lesson"
    for s in ("Слон g5 может отступить на e3.", "Ход Bd3 даёт шах.", "План белых — прорыв f2-f4 и e3-e4? нет."):
        assert not any("cannot go to" in i or "gives no check" in i for i in check_sentence(s, ctx))
