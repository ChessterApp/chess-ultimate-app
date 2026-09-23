#!/usr/bin/env python3
"""Build ``eval/datasets/model_bench_v1.jsonl`` — the live model-comparison set.

Unlike ``golden_v1`` (frozen assistant replies re-scored offline), these cases
are *sent to a live model* through the real /api/coach/chat route by
``scripts/model_bench.py``. Positions come from the golden set; the questions
are the ones our students actually ask, in Russian, Kazakh and English.

    python scripts/build_model_bench_cases.py            # writes the dataset
"""
import json
import random
from pathlib import Path

import chess

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "eval" / "datasets" / "golden_v1.jsonl"
OUT = ROOT / "eval" / "datasets" / "model_bench_v1.jsonl"

rng = random.Random(20260923)

golden = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
# one FEN per golden id, spread across cohorts
seen, fens = set(), []
for g in golden:
    if g["fen"] in seen:
        continue
    seen.add(g["fen"])
    fens.append((g["cohort"], g["fen"]))
rng.shuffle(fens)


def illegal_piece_move(fen: str) -> str:
    """A plausible-looking SAN (piece exists, square empty of own men) that is NOT legal here."""
    board = chess.Board(fen)
    legal = {board.san(m) for m in board.legal_moves}
    for letter, ptype in (("N", chess.KNIGHT), ("Q", chess.QUEEN), ("B", chess.BISHOP), ("R", chess.ROOK)):
        if not board.pieces(ptype, board.turn):
            continue
        squares = list(chess.SQUARES)
        rng.shuffle(squares)
        for sq in squares:
            piece = board.piece_at(sq)
            if piece and piece.color == board.turn:
                continue
            san = f"{letter}{'x' if piece else ''}{chess.square_name(sq)}"
            if san not in legal and san.replace("x", "") not in legal:
                return san
    return "Qh5"


def ru_san(san: str) -> str:
    return san.replace("N", "К").replace("B", "С").replace("R", "Л").replace("Q", "Ф").replace("K", "Кр")


cases = []


def add(cid, kind, message, *, fen=None, locale="ru", expect_lang="ru", expect_tools=(), tags=()):
    cases.append({
        "id": cid, "kind": kind, "message": message, "fen": fen, "locale": locale,
        "expect_lang": expect_lang, "expect_tools": list(expect_tools), "tags": list(tags),
    })


ENGINE = ("analyze_position", "compare_variations", "check_moves", "find_critical_moments")

# ── A. golden positions, Russian ──────────────────────────────────────────
ru_move_q = ["Что мне здесь играть?", "Какой ход посоветуешь и почему?", "Какой здесь лучший ход?"]
ru_assess_q = ["Оцени позицию: кто стоит лучше и почему?", "Как ты оцениваешь эту позицию?"]
i = 0
for n in range(6):
    cohort, fen = fens[i % len(fens)]; i += 1
    add(f"ru-move-{n+1}", "move_recommendation", ru_move_q[n % 3], fen=fen, expect_tools=ENGINE, tags=[cohort])
for n in range(4):
    cohort, fen = fens[i % len(fens)]; i += 1
    add(f"ru-assess-{n+1}", "position_assessment", ru_assess_q[n % 2], fen=fen, expect_tools=ENGINE, tags=[cohort])
for n in range(2):
    cohort, fen = fens[i % len(fens)]; i += 1
    bad = illegal_piece_move(fen)
    add(f"ru-legal-{n+1}", "legality_check", f"Могу ли я сейчас сыграть {ru_san(bad)}?", fen=fen,
        expect_tools=ENGINE, tags=[cohort, f"illegal:{bad}"])

# ── B. Kazakh ─────────────────────────────────────────────────────────────
kk_q = ["Осы жерде қандай жүріс жасаған дұрыс?", "Маған ең жақсы жүрісті ұсыншы және неге екенін түсіндір.",
        "Позицияны бағала: кім жақсы тұр және неге?", "Бұл позицияда менің жоспарым қандай болуы керек?"]
for n in range(4):
    cohort, fen = fens[i % len(fens)]; i += 1
    add(f"kk-{n+1}", "move_recommendation" if n < 2 else "position_assessment", kk_q[n], fen=fen,
        locale="kk", expect_lang="kk", expect_tools=ENGINE, tags=[cohort])

# ── C. English control ────────────────────────────────────────────────────
en_q = ["What should I play here?", "How do you assess this position?", "Which move do you recommend?"]
for n in range(3):
    cohort, fen = fens[i % len(fens)]; i += 1
    add(f"en-{n+1}", "move_recommendation" if n != 1 else "position_assessment", en_q[n], fen=fen,
        locale="en", expect_lang="en", expect_tools=ENGINE, tags=[cohort])

# ── D. puzzles ────────────────────────────────────────────────────────────
add("puzzle-1", "puzzle", "Дай мне задачу на вилку.", expect_tools=("get_puzzle",))
add("puzzle-2", "puzzle", "Дай задачу на мат в 2 хода для начинающего.", expect_tools=("get_puzzle",))
add("puzzle-3", "puzzle", "Хочу потренировать связку, мой рейтинг около 1500. Подбери задачу.", expect_tools=("get_puzzle",))

# ── E. openings ───────────────────────────────────────────────────────────
add("opening-1", "opening", "Что это за дебют и какие планы у белых?",
    fen="rnbqkb1r/1p2pppp/p2p1n2/8/3NP3/2N5/PPP2PPP/R1BQKB1R w KQkq - 0 6",
    expect_tools=("identify_opening", "get_opening_stats"))
add("opening-2", "opening", "Расскажи про итальянскую партию: основные идеи за белых и за чёрных.")
add("opening-3", "opening", "Какие типичные планы у чёрных в этой позиции?",
    fen="r1bqkbnr/pppp1ppp/2n5/1B2p3/4P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
    expect_tools=("identify_opening", "get_opening_stats", *ENGINE))

# ── F. games by position ──────────────────────────────────────────────────
add("games-1", "games_search", "Найди партии сильных шахматистов из этой позиции.",
    fen="rnbqkb1r/pp2pppp/2p2n2/3p4/2PP4/2N5/PP2PPPP/R1BQKBNR w KQkq - 0 4",
    expect_tools=("find_games_by_position",))
add("games-2", "games_search", "Кто из гроссмейстеров играл так за чёрных? Покажи примеры партий.",
    fen="rnbqkb1r/pppp1ppp/4pn2/8/2PP4/8/PP2PPPP/RNBQKBNR w KQkq - 0 3",
    expect_tools=("find_games_by_position",))

# ── G. game review ────────────────────────────────────────────────────────
PGN1 = ("1. e4 e5 2. Nf3 Nc6 3. Bc4 Nf6 4. Ng5 d5 5. exd5 Nxd5 6. Nxf7 Kxf7 7. Qf3+ Ke6 "
        "8. Nc3 Nce7 9. d4 c6 10. Bg5 h6 11. Bxe7 Bxe7 12. O-O-O Rf8 13. Qe4 Rxf2 "
        "14. dxe5 Bg5+ 15. Kb1 Rf4 16. Qd3 Kf7 17. Nxd5 cxd5 18. Qxd5+ Qxd5 19. Bxd5+ Be6 "
        "20. Bxb7 Rb8 21. Bd5 Rxb2+ 22. Kxb2 Bxd5 23. Rxd5 Rf2 24. Rd7+ Kg6 25. Rxa7 Rxg2 0-1")
PGN2 = ("1. d4 d5 2. c4 e6 3. Nc3 Nf6 4. Bg5 Be7 5. e3 O-O 6. Nf3 Nbd7 7. Bd3 c6 8. O-O dxc4 "
        "9. Bxc4 Nd5 10. Bxe7 Qxe7 11. Rc1 Nxc3 12. Rxc3 e5 13. Qc2 exd4 14. exd4 Nb6 "
        "15. Bb3 Bg4 16. Ne5 Bh5 17. Re1 Qd6 18. Nxf7 Bxf7 19. Rxe7 Rae8 20. Rxe8 Rxe8 0-1")
for n, pgn in enumerate((PGN1, PGN2), 1):
    board = chess.Board()
    for tok in pgn.split():
        if tok[0].isdigit():
            continue
        board.push_san(tok)  # raises if the PGN is broken
    add(f"review-{n}", "game_review", f"Разбери мою партию, я играл {'белыми' if n == 1 else 'чёрными'}. Где я ошибся и что надо было играть?\n\n{pgn}",
        expect_tools=("find_critical_moments", "analyze_position", "get_game_insights", "compare_variations"), tags=["long"])

# ── H. coaching without a board ───────────────────────────────────────────
add("coach-1", "general", "Как мне улучшить игру в эндшпиле? Рейтинг около 1300.")
add("coach-2", "general", "Составь план тренировок на неделю, у меня по часу в день, рейтинг 1200.",
    expect_tools=("training_recommender", "get_user_progress"))
add("coach-3", "general", "Что такое связка? Объясни на простом примере.")

# ── I. traps ──────────────────────────────────────────────────────────────
add("trap-1", "legality_check", "Стоит ли мне сейчас сыграть Кxe5?",
    fen="r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3", expect_tools=ENGINE, tags=["illegal:Nxe5"])
add("trap-2", "move_recommendation", "Соперник сыграл Фh5. Как мне правильно защититься?",
    fen="rnbqkbnr/pppp1ppp/8/4p2Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2", expect_tools=ENGINE)
add("trap-3", "position_assessment", "Я тут выигрываю, правда? Как добить?",
    fen="6k1/5ppp/8/8/8/8/5PPP/3R2K1 b - - 0 1", expect_tools=ENGINE, tags=["losing-side"])

# ── J. external import ────────────────────────────────────────────────────
add("import-1", "import", "Покажи мои последние партии на lichess, мой ник DrNykterstein, и скажи, какой дебют я играю чаще всего.",
    expect_tools=("lichess_game_import",))

OUT.write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in cases) + "\n", encoding="utf-8")
print(f"{len(cases)} cases -> {OUT.relative_to(ROOT)}")
