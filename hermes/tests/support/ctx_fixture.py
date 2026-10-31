"""A CheckContext as JSON, and an answer run through it (plan 31.10, WP-0).

The fixtures of tests/fixtures/detect1031/rows/ hold the context of a replayed turn as it was when the answer check
began (the boards with their move stacks, the keys, the game, the records, the engine's evaluation …), serialised
here — JSON, not pickle, so a new ctx field does not break them. ``run_answer`` then checks the answer's sentences
in order, so the scene, the antecedents and the told lines build up exactly as on the server.

  dump_ctx(ctx) -> dict          load_ctx(path or dict) -> CheckContext
  run_answer(answer, ctx, engine=False) -> [(sentence, issues, stage)]
"""
from __future__ import annotations

import dataclasses
import importlib
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional, Union

import chess

FORMAT = 1


# ── serialisation ────────────────────────────────────────────────────────────────────────────────────────────────
def _board_dict(b: chess.Board) -> dict:
    root = b.root()
    return {"root": root.fen(), "moves": [m.uci() for m in b.move_stack], "fen": b.fen()}


def _board_from(d: dict) -> chess.Board:
    b = chess.Board(d["root"])
    for u in d.get("moves") or ():
        b.push(chess.Move.from_uci(u))
    if b.fen() != d.get("fen", b.fen()):
        raise ValueError(f"board did not rebuild: {b.fen()} != {d['fen']}")
    return b


def _sort_key(x: Any) -> str:
    return json.dumps(x, ensure_ascii=False, sort_keys=True)


class _Enc:
    def __init__(self):
        self.memo: dict = {}
        self.boards: list = []

    def __call__(self, v: Any) -> Any:
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        if isinstance(v, chess.Board):
            i = self.memo.get(id(v))
            if i is None:
                i = self.memo[id(v)] = len(self.boards)
                self.boards.append(_board_dict(v))
            return {"$b": i}
        if isinstance(v, chess.Move):
            return {"$m": v.uci()}
        if isinstance(v, chess.Piece):
            return {"$p": v.symbol()}
        if isinstance(v, tuple):
            return {"$t": [self(x) for x in v]}
        if isinstance(v, list):
            return [self(x) for x in v]
        if isinstance(v, (set, frozenset)):
            return {"$s": sorted((self(x) for x in v), key=_sort_key)}
        if isinstance(v, dict):
            return {"$d": [[self(k), self(x)] for k, x in v.items()]}
        if dataclasses.is_dataclass(v) and not isinstance(v, type):
            cls = type(v)
            return {"$dc": f"{cls.__module__}:{cls.__qualname__}",
                    "f": {f.name: self(getattr(v, f.name)) for f in dataclasses.fields(v)}}
        raise TypeError(f"cannot serialise {type(v).__name__}")


class _Dec:
    def __init__(self, boards: list):
        self.raw = boards
        self.built: dict = {}

    def board(self, i: int) -> chess.Board:
        if i not in self.built:
            self.built[i] = _board_from(self.raw[i])
        return self.built[i]

    def __call__(self, v: Any) -> Any:
        if isinstance(v, list):
            return [self(x) for x in v]
        if not isinstance(v, dict):
            return v
        if "$b" in v:
            return self.board(v["$b"])
        if "$m" in v:
            return chess.Move.from_uci(v["$m"])
        if "$p" in v:
            return chess.Piece.from_symbol(v["$p"])
        if "$t" in v:
            return tuple(self(x) for x in v["$t"])
        if "$s" in v:
            return {self(x) for x in v["$s"]}
        if "$d" in v:
            return {self(k): self(x) for k, x in v["$d"]}
        if "$dc" in v:
            mod, name = v["$dc"].split(":")
            cls = getattr(importlib.import_module(mod), name)
            return cls(**{k: self(x) for k, x in v["f"].items()})
        raise ValueError(f"unknown tagged value {list(v)[:3]}")


def dump_ctx(ctx) -> dict:
    """The context as JSON-ready data: every attribute (dataclass fields and the ones modules set on it), boards with
    their move stacks, shared boards kept shared (ctx.current is one of ctx.boards)."""
    enc = _Enc()
    attrs = {}
    names = [f.name for f in dataclasses.fields(ctx)] + [k for k in vars(ctx) if k not in {f.name for f in dataclasses.fields(ctx)}]
    for name in names:
        try:
            attrs[name] = enc(getattr(ctx, name))
        except TypeError as exc:
            raise TypeError(f"ctx.{name}: {exc}") from None
    return {"format": FORMAT, "boards": enc.boards, "attrs": attrs}


def load_ctx(src: Union[str, Path, dict]):
    """A CheckContext from dump_ctx's data, or from a fixture file holding it under "ctx"."""
    from src.answer_check import CheckContext

    data = src
    if not isinstance(src, dict):
        data = json.loads(Path(src).read_text(encoding="utf-8"))
    if "ctx" in data and "attrs" not in data:
        data = data["ctx"]
    dec = _Dec(data["boards"])
    ctx = CheckContext()
    for name, v in data["attrs"].items():
        setattr(ctx, name, dec(v))
    return ctx


# ── running an answer ────────────────────────────────────────────────────────────────────────────────────────────
@contextmanager
def _recording():
    """Every sentence the gate checks, with its issues, in order."""
    from src import answer_check

    seen: list = []
    orig = answer_check.check_sentence

    def rec(sentence, ctx=None, *a, **k):
        issues = orig(sentence, ctx, *a, **k)
        seen.append((sentence, list(issues or [])))
        return issues

    answer_check.check_sentence = rec
    try:
        yield seen
    finally:
        answer_check.check_sentence = orig


def _sentences(answer: Union[str, Iterable[str]], ctx, chunk: int) -> list:
    """(sentence, sync issues) in order: a list is checked as given; a text goes through the server's SentenceGate in
    *chunk*-character deltas (the replay streams 7)."""
    from src import answer_check

    if not isinstance(answer, str):
        return [(s, list(answer_check.check_sentence(s, ctx) or [])) for s in answer]
    with _recording() as seen:
        gate = answer_check.SentenceGate(ctx, enabled=True, hold_promises=True)
        for i in range(0, len(answer), chunk):
            gate.feed(answer[i:i + chunk])
        gate.flush()
    return seen


def _engine_issue(sentence: str, ctx, state: dict, live_game: bool) -> Optional[str]:
    """The server's engine stage for one sentence the sync check passed (src/server.py _verified): the recommendation,
    the outcome of a written line, a forced reply — within COACH_MOVE_VERIFY_PER_TURN checks per answer."""
    from src import config
    from src.answer_check import proposed_move, written_line_after
    from src.hypothetical import verify_forced_reply, verify_recommendation

    if state["left"] <= 0 or ctx.current is None:
        return None
    ms, cp, reveal = config.COACH_MOVE_VERIFY_MOVETIME_MS, config.COACH_MOVE_VERIFY_CP, not live_game
    issue = None
    found = proposed_move(sentence, ctx)
    if found:
        state["left"] -= 1
        issue = verify_recommendation(found[0], found[1], found[2], ms, cp, reveal, written_line_after(sentence, found[2]))
    claims = ctx.line_claims.pop(sentence, None)
    if claims and not issue and state["left"] > 0 and config.COACH_LINE_VERDICT:
        from src.line_verdict import verify_claims

        state["left"] -= 1
        issue = verify_claims(claims, ms, reveal)
    if not issue and state["left"] > 0:
        claim = ctx.forced_claims.get(sentence)
        if claim:
            state["left"] -= 1
            issue = verify_forced_reply(claim, ms, reveal)
    return issue


def run_answer(answer: Union[str, Iterable[str]], ctx, *, engine: bool = False, live_game: Optional[bool] = None,
               chunk: int = 7) -> list:
    """Check *answer* (a text, or its sentences in order) on *ctx*: [(sentence, issues, stage)], stage 'sync' when the
    sentence check cut it, 'engine' when the engine stage did (only with *engine*; Stockfish runs locally), '' when
    it is shown. *live_game* defaults to "a game is on the board" (ctx.game_engine_moves set), as on the server."""
    from src import config

    if live_game is None:
        live_game = getattr(ctx, "game_engine_moves", None) is not None
    state = {"left": config.COACH_MOVE_VERIFY_PER_TURN if config.COACH_MOVE_VERIFY else 0}
    out = []
    for sentence, issues in _sentences(answer, ctx, chunk):
        if issues:
            out.append((sentence, issues, "sync"))
            continue
        if engine:
            issue = _engine_issue(sentence, ctx, state, live_game)
            if issue:
                out.append((sentence, [issue], "engine"))
                continue
        out.append((sentence, [], ""))
    return out
