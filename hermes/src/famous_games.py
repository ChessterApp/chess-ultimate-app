"""Famous games named in a message, from verified scores (2026-10-08).

«Покажи оперную партию Морфи» (production 08.10): the master-games database starts in 1994, the coach
took some other game from it, the board refused it, and the answer told the Opera Game from memory —
«он отдаёт слонов» where Morphy gave a knight, a rook, a bishop and his queen. Like an opening named
by its name (src/opening_knowledge.py), a famous game named in the message goes on the board before
the model answers, with its moves and what each side gave up, counted by python-chess.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import chess
import chess.pgn

# name, how students call it (ru/en/kk word starts), headers, movetext.
GAMES = [
    {
        "key": "opera",
        "name": "Opera Game (Оперная партия)",
        "match": r"опер(?:н|а\s|е\s|у\s|ой)|opera\s+game|в\s+опере",
        "white": "Paul Morphy", "black": "Duke Karl of Brunswick and Count Isouard",
        "event": "Paris Opera", "date": "1858.??.??", "result": "1-0",
        "moves": "1.e4 e5 2.Nf3 d6 3.d4 Bg4 4.dxe5 Bxf3 5.Qxf3 dxe5 6.Bc4 Nf6 7.Qb3 Qe7 8.Nc3 c6 9.Bg5 b5 "
                 "10.Nxb5 cxb5 11.Bxb5+ Nbd7 12.O-O-O Rd8 13.Rxd7 Rxd7 14.Rd1 Qe6 15.Bxd7+ Nxd7 16.Qb8+ Nxb8 17.Rd8#",
    },
    {
        "key": "kasparov-topalov",
        "name": "Kasparov's Immortal (Каспаров — Топалов, Вейк-ан-Зее 1999)",
        "match": r"каспаров\w*[^.?!]{0,30}топалов|топалов\w*[^.?!]{0,30}каспаров|бессмертн\w*\s+(?:парти\w+\s+)?каспаров|"
                 r"kasparov'?s\s+immortal|kasparov[^.?!]{0,20}topalov",
        "white": "Garry Kasparov", "black": "Veselin Topalov",
        "event": "Hoogovens, Wijk aan Zee", "date": "1999.01.20", "result": "1-0",
        "moves": "1.e4 d6 2.d4 Nf6 3.Nc3 g6 4.Be3 Bg7 5.Qd2 c6 6.f3 b5 7.Nge2 Nbd7 8.Bh6 Bxh6 9.Qxh6 Bb7 "
                 "10.a3 e5 11.O-O-O Qe7 12.Kb1 a6 13.Nc1 O-O-O 14.Nb3 exd4 15.Rxd4 c5 16.Rd1 Nb6 17.g3 Kb8 "
                 "18.Na5 Ba8 19.Bh3 d5 20.Qf4+ Ka7 21.Rhe1 d4 22.Nd5 Nbxd5 23.exd5 Qd6 24.Rxd4 cxd4 25.Re7+ Kb6 "
                 "26.Qxd4+ Kxa5 27.b4+ Ka4 28.Qc3 Qxd5 29.Ra7 Bb7 30.Rxb7 Qc4 31.Qxf6 Kxa3 32.Qxa6+ Kxb4 "
                 "33.c3+ Kxc3 34.Qa1+ Kd2 35.Qb2+ Kd1 36.Bf1 Rd2 37.Rd7 Rxd7 38.Bxc4 bxc4 39.Qxh8 Rd3 40.Qa8 c3 "
                 "41.Qa4+ Ke1 42.f4 f5 43.Kc1 Rd2 44.Qa7",
    },
    {
        "key": "immortal",
        "name": "Immortal Game (Бессмертная партия)",
        "match": r"бессмертн|immortal\s+game|андерсен\w*[^.?!]{0,30}кизериц|кизериц\w*|anderssen[^.?!]{0,20}kieseritzky|өлмес",
        "white": "Adolf Anderssen", "black": "Lionel Kieseritzky",
        "event": "London", "date": "1851.06.21", "result": "1-0",
        "moves": "1.e4 e5 2.f4 exf4 3.Bc4 Qh4+ 4.Kf1 b5 5.Bxb5 Nf6 6.Nf3 Qh6 7.d3 Nh5 8.Nh4 Qg5 9.Nf5 c6 "
                 "10.g4 Nf6 11.Rg1 cxb5 12.h4 Qg6 13.h5 Qg5 14.Qf3 Ng8 15.Bxf4 Qf6 16.Nc3 Bc5 17.Nd5 Qxb2 "
                 "18.Bd6 Bxg1 19.e5 Qxa1+ 20.Ke2 Na6 21.Nxg7+ Kd8 22.Qf6+ Nxf6 23.Be7#",
    },
    {
        "key": "evergreen",
        "name": "Evergreen Game (Вечнозелёная партия)",
        "match": r"вечнозел[её]н|evergreen|андерсен\w*[^.?!]{0,30}дюфрен|дюфрен|anderssen[^.?!]{0,20}dufresne",
        "white": "Adolf Anderssen", "black": "Jean Dufresne",
        "event": "Berlin", "date": "1852.??.??", "result": "1-0",
        "moves": "1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.b4 Bxb4 5.c3 Ba5 6.d4 exd4 7.O-O d3 8.Qb3 Qf6 9.e5 Qg6 "
                 "10.Re1 Nge7 11.Ba3 b5 12.Qxb5 Rb8 13.Qa4 Bb6 14.Nbd2 Bb7 15.Ne4 Qf5 16.Bxd3 Qh5 17.Nf6+ gxf6 "
                 "18.exf6 Rg8 19.Rad1 Qxf3 20.Rxe7+ Nxe7 21.Qxd7+ Kxd7 22.Bf5+ Ke8 23.Bd7+ Kf8 24.Bxe7#",
    },
    {
        # The coach told it «вничью» from memory (prod, 23.10): Carlsen won it, 136 moves, the longest game of any
        # title match. Named with the game number or «самая длинная»; «2-ю партию Карлсен — Непомнящий» is not it.
        "key": "wch2021-g6",
        "name": "World Championship 2021, game 6 (Карлсен — Непомнящий, Дубай 2021, 136 ходов)",
        "match": r"(?:(?:\b6(?:-?[а-я]{1,2})?|шест\w*|136|сам\w+\s+длинн\w*|longest|sixth|six)\s+(?:[\w-]+\s+){0,6}?(?:карлсен|непомнящ|carlsen|nepo)"
                 r"|(?:карлсен|непомнящ|carlsen|nepo)\w*\s+(?:[\w\-—–]+\s+){0,8}?(?:6(?:-?[а-я]{1,2})?\b|шест\w*|136|сам\w+\s+длинн\w*|longest|sixth|six\b))",
        "white": "Magnus Carlsen", "black": "Ian Nepomniachtchi",
        "event": "World Chess Championship, Dubai, game 6", "date": "2021.12.03", "result": "1-0",
        "moves": "1.d4 Nf6 2.Nf3 d5 3.g3 e6 4.Bg2 Be7 5.O-O O-O 6.b3 c5 7.dxc5 Bxc5 8.c4 dxc4 9.Qc2 Qe7 10.Nbd2 Nc6 "
                 "11.Nxc4 b5 12.Nce5 Nb4 13.Qb2 Bb7 14.a3 Nc6 15.Nd3 Bb6 16.Bg5 Rfd8 17.Bxf6 gxf6 18.Rac1 Nd4 "
                 "19.Nxd4 Bxd4 20.Qa2 Bxg2 21.Kxg2 Qb7+ 22.Kg1 Qe4 23.Qc2 a5 24.Rfd1 Kg7 25.Rd2 Rac8 26.Qxc8 Rxc8 "
                 "27.Rxc8 Qd5 28.b4 a4 29.e3 Be5 30.h4 h5 31.Kh2 Bb2 32.Rc5 Qd6 33.Rd1 Bxa3 34.Rxb5 Qd7 35.Rc5 e5 "
                 "36.Rc2 Qd5 37.Rdd2 Qb3 38.Ra2 e4 39.Nc5 Qxb4 40.Nxe4 Qb3 41.Rac2 Bf8 42.Nc5 Qb5 43.Nd3 a3 44.Nf4 Qa5 "
                 "45.Ra2 Bb4 46.Rd3 Kh6 47.Rd1 Qa4 48.Rda1 Bd6 49.Kg1 Qb3 50.Ne2 Qd3 51.Nd4 Kh7 52.Kh2 Qe4 53.Rxa3 Qxh4+ "
                 "54.Kg1 Qe4 55.Ra4 Be5 56.Ne2 Qc2 57.R1a2 Qb3 58.Kg2 Qd5+ 59.f3 Qd1 60.f4 Bc7 61.Kf2 Bb6 62.Ra1 Qb3 "
                 "63.Re4 Kg7 64.Re8 f5 65.Raa8 Qb4 66.Rac8 Ba5 67.Rc1 Bb6 68.Re5 Qb3 69.Re8 Qd5 70.Rcc8 Qh1 71.Rc1 Qd5 "
                 "72.Rb1 Ba7 73.Re7 Bc5 74.Re5 Qd3 75.Rb7 Qc2 76.Rb5 Ba7 77.Ra5 Bb6 78.Rab5 Ba7 79.Rxf5 Qd3 80.Rxf7+ Kxf7 "
                 "81.Rb7+ Kg6 82.Rxa7 Qd5 83.Ra6+ Kh7 84.Ra1 Kg6 85.Nd4 Qb7 86.Ra2 Qh1 87.Ra6+ Kf7 88.Nf3 Qb1 89.Rd6 Kg7 "
                 "90.Rd5 Qa2+ 91.Rd2 Qb1 92.Re2 Qb6 93.Rc2 Qb1 94.Nd4 Qh1 95.Rc7+ Kf6 96.Rc6+ Kf7 97.Nf3 Qb1 98.Ng5+ Kg7 "
                 "99.Ne6+ Kf7 100.Nd4 Qh1 101.Rc7+ Kf6 102.Nf3 Qb1 103.Rd7 Qb2+ 104.Rd2 Qb1 105.Ng1 Qb4 106.Rd1 Qb3 "
                 "107.Rd6+ Kg7 108.Rd4 Qb2+ 109.Ne2 Qb1 110.e4 Qh1 111.Rd7+ Kg8 112.Rd4 Qh2+ 113.Ke3 h4 114.gxh4 Qh3+ "
                 "115.Kd2 Qxh4 116.Rd3 Kf8 117.Rf3 Qd8+ 118.Ke3 Qa5 119.Kf2 Qa7+ 120.Re3 Qd7 121.Ng3 Qd2+ 122.Kf3 Qd1+ "
                 "123.Re2 Qb3+ 124.Kg2 Qb7 125.Rd2 Qb3 126.Rd5 Ke7 127.Re5+ Kf7 128.Rf5+ Ke8 129.e5 Qa2+ 130.Kh3 Qe6 "
                 "131.Kh4 Qh6+ 132.Nh5 Qh7 133.e6 Qg6 134.Rf7 Kd8 135.f5 Qg1 136.Ng7",
    },
    {
        "key": "game-of-the-century",
        "name": "Game of the Century (Партия века)",
        "match": r"парти\w+\s+века|game\s+of\s+the\s+century|бирн\w*[^.?!]{0,30}фишер|фишер\w*[^.?!]{0,30}бирн|byrne[^.?!]{0,20}fischer",
        "white": "Donald Byrne", "black": "Robert James Fischer",
        "event": "Rosenwald Memorial, New York", "date": "1956.10.17", "result": "0-1",
        "moves": "1.Nf3 Nf6 2.c4 g6 3.Nc3 Bg7 4.d4 O-O 5.Bf4 d5 6.Qb3 dxc4 7.Qxc4 c6 8.e4 Nbd7 9.Rd1 Nb6 "
                 "10.Qc5 Bg4 11.Bg5 Na4 12.Qa3 Nxc3 13.bxc3 Nxe4 14.Bxe7 Qb6 15.Bc4 Nxc3 16.Bc5 Rfe8+ 17.Kf1 Be6 "
                 "18.Bxb6 Bxc4+ 19.Kg1 Ne2+ 20.Kf1 Nxd4+ 21.Kg1 Ne2+ 22.Kf1 Nc3+ 23.Kg1 axb6 24.Qb4 Ra4 "
                 "25.Qxb6 Nxd1 26.h3 Rxa2 27.Kh2 Nxf2 28.Re1 Rxe1 29.Qd8+ Bf8 30.Nxe1 Bd5 31.Nf3 Ne4 32.Qb8 b5 "
                 "33.h4 h5 34.Ne5 Kg7 35.Kg1 Bc5+ 36.Kf1 Ng3+ 37.Ke1 Bb4+ 38.Kd1 Bb3+ 39.Kc1 Ne2+ 40.Kb1 Nc3+ "
                 "41.Kc1 Rc2#",
    },
]


def _pgn(g: dict) -> str:
    return (f'[Event "{g["event"]}"]\n[Date "{g["date"]}"]\n[White "{g["white"]}"]\n[Black "{g["black"]}"]\n'
            f'[Result "{g["result"]}"]\n\n{g["moves"]} {g["result"]}')


def _replay(g: dict) -> tuple[chess.pgn.Game, list]:
    game = chess.pgn.read_game(io.StringIO(_pgn(g)))
    return game, list(game.mainline_moves())


def facts(g: dict) -> str:
    """What each side gave up, move by move, and how it ends — counted on the board."""
    game, moves = _replay(g)
    board = game.board()
    lost = {chess.WHITE: [], chess.BLACK: []}
    for n, mv in enumerate(moves):
        victim = board.piece_at(mv.to_square) if not board.is_en_passant(mv) else chess.Piece(chess.PAWN, not board.turn)
        if victim is not None and victim.piece_type != chess.PAWN:
            label = f"{chess.piece_name(victim.piece_type)} {chess.square_name(mv.to_square)} (move {n // 2 + 1})"
            lost[victim.color].append(label)
        board.push(mv)
    if board.is_checkmate():
        end = f"it ends in mate: {game.end().san()} — the last move."
    else:
        end = f"it ends with {game.headers.get('Result')} after the last move {game.end().san()}."
    return (f"Pieces White lost: {', '.join(lost[chess.WHITE]) or 'none'}. "
            f"Pieces Black lost: {', '.join(lost[chess.BLACK]) or 'none'}. The game has {len(moves)} half-moves; {end}")


def famous_game(message: str, hidden: bool = False) -> Optional[dict]:
    """{"key", "name", "pgn", "block", "hidden"} for a famous game the message names, or None.

    *hidden*: the student's own position stays on the board (src/question_position, 2026-10-20) — the
    game is told from its moves and offered, not loaded.
    """
    text = (message or "").lower().replace("ё", "е")
    for g in GAMES:
        # From the start of a word: «опер…» found the Opera game inside «сОПЕРНика» and put it on the
        # board for «у соперника остался только король — кто победил?» (prod, 2026-10-13).
        if re.search(r"(?<![\w-])(?:" + g["match"].replace("ё", "е") + ")", text):
            pgn = _pgn(g)
            where = ("on a HIDDEN board — NOT on the student's (their own position stays in front of them)" if hidden
                     else "ALREADY on the board")
            tail = (
                "The game is NOT on the student's board: do not call it «the board», draw no arrows; tell it from "
                "these moves and facts, and offer to put it on the board — a short «покажи» will do it. Do not "
                "search for it."
                if hidden else
                "The game is on the student's board: do not load it again, do not search for it."
            )
            block = (
                f"## The famous game the student asked about — {g['name']}, verified score, {where}\n"
                f"{g['white']} – {g['black']}, {g['event']}, {g['date'][:4]}. Moves: {g['moves']} {g['result']}\n"
                f"{facts(g)}\n"
                f"{tail} Tell it from these "
                "moves and facts only — every capture, sacrifice and the final blow are above; never add a move, a "
                "capture or a piece that is not in them."
            )
            return {"key": g["key"], "name": g["name"], "pgn": pgn, "block": block, "hidden": hidden}
    return None
