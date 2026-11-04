#!/usr/bin/env python3
"""Prevention proxies of plan 31.10 (§5.2 a–e), deterministic: are the facts the model gets true, and do they carry
the truth that contradicts the graded errors of 29.10?

  (a) truth audit — every outcome fact given on the corpus positions (tests/fixtures/detect1031/corpus_positions.json,
      318; game_positions.json, every ply of the game corpus's games, scripts/build_game_positions.py) checked by
      Stockfish at --depth (default 18): the fork facts
      of today's prompt paths (prompt_builder.board_facts_block, voice_engine_note._facts) and the typed facts of
      src/turn_facts when P8's provider exists (turn_facts.facts_for_board(board, engine_lines) -> [Fact]).
      Gates: 0 false outcome facts (typed), fork facts bad ≤ 5 % of those kept, every "safe square" holds.
  (b) poisoned prompts — of the 89 graded errors, the turns whose model message carries a fact that supports the
      error (tests/fixtures/prevent/antidotes.json "poison"). Gate: 0.
  (c) antidote coverage — per class, the turns whose message carries the truth ("antidote"): present / absent /
      wrong fact present. Gate: the 8 prevent-only rows covered, and no covered row lost against --base-run.
  (d) prompt cost — characters added to the model message per turn against --base-run (replay1031 of main):
      board turns median ≤ +600, p95 ≤ +1,500; turns without a board +0; provider time p99 ≤ 5 ms (the replay's
      "facts_ms", when the run measured it).
  (e) issue-text antidotes — every row this run cuts and the base did not: its issue names the truth ("issue").
      "The base did not" is a majority over the base runs, not one run: main's engine stage misses trap-legal about one
      run in three (verify1102 §4), and one such miss made that row look new. The base runs are the base columns of
      every --analysis given (each one this run's analysis against another run of the base), plus a recorded baseline
      (--base-caught, default tests/fixtures/prevent/main_caught.json: the rows main 02bb40d0 cut in each of its
      recorded replay1031 runs). A row is the base's when it cut it in at least half of all those runs.

Usage (from hermes/):
  python scripts/eval_prevent.py --run R.json --analysis R_analysis.json [B2_analysis.json ...] [--base-run B.json]
         [--base-caught main_caught.json | --base-caught none] [--audit] [--depth 18] [--gate] [--json out.json]
  python scripts/eval_prevent.py --record-base-caught OUT.json --analysis A1.json A2.json A3.json [--base-tree SHA]
  R.json is a replay1031 run (scratchpad …/prod1029/replay1031/replay.py), R_analysis.json its analyze.py output
  against the base (verify1031/replay_on.json or a replay1031 run of main); further analyses add their base runs to
  the majority of (e). --record-base-caught writes the recorded baseline from the base columns of the analyses.
  --audit runs (a) (minutes: Stockfish).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

H = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(H))
FIX = H / "tests" / "fixtures"

import chess  # noqa: E402

FORK = re.compile(r"a fork is available now: (?P<san>\S+?) attacks")
BAD_LOSS = 1.5  # pawns: a fork move that loses this much against the best move is a bad fact (triage-eval)
MATE = 100.0


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else None


# ── (a) the truth audit ────────────────────────────────────────────────────────────────────────────────────────
class Engine:
    def __init__(self, depth: int):
        import chess.engine

        from src.tools.stockfish import STOCKFISH_PATH

        self.e = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        self.e.configure({"Threads": 1, "Hash": 64})
        self.depth = depth
        self.cache: dict = {}

    def score(self, board: chess.Board) -> float:
        """Pawns for the side to move, mates as ±100."""
        key = board.fen()
        if key not in self.cache:
            import chess.engine

            if board.is_checkmate():
                self.cache[key] = -MATE
            elif board.is_stalemate() or board.is_insufficient_material():
                self.cache[key] = 0.0
            else:
                info = self.e.analyse(board, chess.engine.Limit(depth=self.depth))
                self.cache[key] = info["score"].pov(board.turn).score(mate_score=10000) / 100.0
        return self.cache[key]

    def loss(self, board: chess.Board, move: chess.Move) -> float:
        best = self.score(board)
        after = board.copy(stack=False)
        after.push(move)
        return round(best - (-self.score(after)), 2)

    def quit(self):
        self.e.quit()


def _positions() -> list:
    out = []
    for name in ("corpus_positions.json", "game_positions.json"):
        p = FIX / "detect1031" / name
        if p.exists():
            for x in json.loads(p.read_text(encoding="utf-8"))["positions"]:
                out.append((name.split("_")[0], x["name"], x["fen"]))
    return out


ENGINE_MOVETIME_MS: int | None = None  # --engine-movetime; None: the turn's own (COACH_ENGINE_NOTE_MOVETIME_MS)


def _prompt_facts(board: chess.Board) -> dict:
    """The fact lines today's two prompt paths give for *board*: the board-only block and the engine line's facts —
    the engine path as production builds it (DEFAULT_MULTIPV lines at the turn's movetime: the forks are vetted against
    all of them; review-wiring 01.11: one depth-12 line was stricter than production)."""
    from src import config
    from src.prompt_builder import board_facts_block
    from src.tools.stockfish import DEFAULT_MULTIPV, analyze_timed
    from src.voice_engine_note import _facts

    out = {"board": [], "engine": []}
    block = board_facts_block(board.fen()) or ""
    out["board"] = [ln[2:] for ln in block.splitlines() if ln.startswith("- ")]
    try:
        movetime = ENGINE_MOVETIME_MS or config.COACH_ENGINE_NOTE_MOVETIME_MS
        res = analyze_timed(board.fen(), movetime, multipv=DEFAULT_MULTIPV)
        lines = res.get("lines") or []
        out["engine"] = _facts(board, lines[0], None, lines=lines) if lines else []
    except Exception:  # noqa: BLE001
        out["engine"] = []
    return out


def _typed_facts(board: chess.Board) -> list:
    from src import turn_facts

    provider = getattr(turn_facts, "facts_for_board", None)
    if provider is None:
        return []
    try:
        return list(provider(board, None) or [])
    except Exception as exc:  # noqa: BLE001
        print(f"  turn_facts.facts_for_board failed on {board.fen()}: {exc!r}")
        return []


def audit(depth: int, limit: int | None) -> dict:
    from src import board_math

    eng = Engine(depth)
    forks, typed, unproven, bad_typed = [], 0, [], []
    seen = set()
    t0 = time.monotonic()
    try:
        for src, name, fen in _positions()[:limit]:
            board = chess.Board(fen)
            if board.epd() in seen or not board.is_valid():
                continue
            seen.add(board.epd())
            facts = _prompt_facts(board)
            told = {}
            for path, lines in facts.items():
                for ln in lines:
                    m = FORK.search(ln)
                    if m:
                        told.setdefault(m["san"], []).append(path)
            for san, paths in told.items():
                try:
                    mv = board.parse_san(san)
                except ValueError:
                    forks.append({"pos": name, "fen": fen, "fork": san, "paths": paths, "loss": None, "illegal": True})
                    continue
                forks.append({"pos": name, "fen": fen, "fork": san, "paths": sorted(set(paths)),
                              "loss": eng.loss(board, mv)})
            for f in _typed_facts(board):
                typed += 1
                if not f.proven:
                    unproven.append({"fen": fen, "fact": f.to_dict()})
                    continue
                if f.kind == "fork" and f.data.get("san"):
                    mv = board.parse_san(f.data["san"])
                    if eng.loss(board, mv) >= BAD_LOSS:
                        bad_typed.append({"fen": fen, "fact": f.to_dict(), "why": "the fork move loses"})
                elif f.kind == "piece_safety":
                    sq = chess.parse_square(f.data["sq"])
                    for s in f.data.get("safe") or []:
                        mv = next((m for m in board_math.legal_moves_of(board, sq) if chess.square_name(m.to_square) == s), None)
                        b = board_math._as_side(board, board.piece_at(sq).color) if board.piece_at(sq) else None
                        if mv is None or b is None or board_math.move_loss(b, mv) > 0 or eng.loss(b, mv) >= BAD_LOSS:
                            bad_typed.append({"fen": fen, "fact": f.to_dict(), "why": f"{s} is not safe"})
    finally:
        eng.quit()
    bad = [f for f in forks if f.get("illegal") or (f["loss"] is not None and f["loss"] >= BAD_LOSS)]
    return {"positions": len(seen), "depth": depth, "seconds": round(time.monotonic() - t0, 1),
            "fork_facts": len(forks), "fork_facts_bad": len(bad),
            "fork_bad_rate": round(len(bad) / len(forks), 3) if forks else 0.0,
            "forks": forks,
            "typed_facts": typed, "typed_unproven": len(unproven), "typed_false": len(bad_typed),
            "bad_forks": bad, "unproven": unproven[:50], "false_typed": bad_typed[:50]}


# ── (b)–(e) over a replay run ─────────────────────────────────────────────────────────────────────────────────
def _turns(run: dict) -> dict:
    return {r["id"]: r for r in run["results"] if "cuts" in r}


def _labels() -> list:
    return json.loads((FIX / "prevent" / "antidotes.json").read_text(encoding="utf-8"))["findings"]


def _row_of(table: list, lab: dict):
    for t in table:
        if t["src"] == lab["src"] and t["id"] == lab["id"] and t["kind"] == lab["kind"] and t["quote"].startswith(lab["quote_start"]):
            return t
    return None


_ENGINE_LINE = re.compile(r"^\[Engine\][^\n]*$", re.MULTILINE)


def _without_engine(text):
    """*text* without the engine's own lines («[Engine] … Best: d4 (+0.26; line d4 d5 e5 Bf5)»)."""
    return _ENGINE_LINE.sub("", text or "")


def _hits(patterns, text) -> bool:
    return any(re.search(p, text or "", re.IGNORECASE | re.DOTALL) for p in patterns or [])


def _row_key(t: dict) -> str:
    """A graded row of analyze.py's table: an answer can hold two errors of one class, told apart by the quote."""
    return f"{t['src']}/{t['id']}/{t['kind']}/{re.sub(r'\s+', ' ', t['quote'])[:80]}"


def base_votes(analyses: list, recorded: dict | None) -> dict:
    """Per table row (src/id/kind): (runs of the base that cut it, runs of the base) over the base column of every
    analysis and the recorded baseline's runs."""
    votes: dict = {}
    for an in analyses:
        for t in an["table"]:
            k = _row_key(t)
            c, n = votes.get(k, (0, 0))
            votes[k] = (c + bool(t["base"]), n + 1)
    if recorded:
        for k, c in recorded["rows"].items():
            c0, n0 = votes.get(k, (0, 0))
            votes[k] = (c0 + c, n0 + recorded["runs"])
        for k in list(votes):
            if k not in recorded["rows"]:  # a row the recorded runs never cut: they count as misses
                c0, n0 = votes[k]
                votes[k] = (c0, n0 + recorded["runs"])
    return votes


def base_cut(votes: dict, key: str) -> bool:
    """The base cuts the row: in at least half of its runs (no runs: no)."""
    cut, runs = votes.get(key, (0, 0))
    return runs > 0 and 2 * cut >= runs


def record_base_caught(analyses: list, tree: str | None) -> dict:
    rows: dict = {}
    for an in analyses:
        for t in an["table"]:
            rows.setdefault(_row_key(t), 0)
            rows[_row_key(t)] += bool(t["base"])
    return {"doc": "Rows of the 89 graded errors the base cut, per row the number of its recorded replay1031 runs that "
                   "cut it (eval_prevent.py (e): a row is the base's when it cut it in at least half of all runs).",
            "tree": tree, "runs": len(analyses), "rows": {k: c for k, c in sorted(rows.items()) if c}}


def _class(lab) -> str:
    return f"games {lab['src']}" if lab["src"] != "sets" else f"sets {lab['kind']}"


def prompts(run: dict, analysis: dict, base: dict | None, more_analyses: list | None = None,
            recorded: dict | None = None) -> dict:
    turns, bturns = _turns(run), (_turns(base) if base else {})
    table = analysis["table"]
    votes = base_votes([analysis] + list(more_analyses or []), recorded)
    rows, by_class = [], {}
    for lab in _labels():
        t = _row_of(table, lab)
        r = turns.get(lab["id"]) or {}
        msg = r.get("model_message")
        bmsg = (bturns.get(lab["id"]) or {}).get("model_message") if base else None
        row = {"src": lab["src"], "id": lab["id"], "kind": lab["kind"], "prevent_only": lab["prevent_only"],
               "has_message": msg is not None,
               "poisoned": _hits(lab["poison"], msg),
               "covered": _hits(lab["antidote"], msg) if lab["antidote"] else None,
               "covered_base": (_hits(lab["antidote"], bmsg) if lab["antidote"] and bmsg is not None else None),
               # the antidote in the base outside the engine's own line: an antidote only the engine line carries comes and
               # goes with the line the search picks (review-wiring2 01.11: Bf5 in «line d4 d5 e5 Bf5»), not lost
               "covered_base_fact": (_hits(lab["antidote"], _without_engine(bmsg)) if lab["antidote"] and bmsg is not None
                                     else None),
               "caught": bool(t and t["branch"]), "caught_base_run": bool(t and t["base"]),
               # the base's cut by majority over its runs (one flaky miss of the paired base run is not a new cut)
               "caught_base": bool(t) and base_cut(votes, _row_key(t)),
               "base_votes": list(votes.get(_row_key(t), (0, 0))) if t else None,
               "issue": (t or {}).get("branch_issue"),
               "issue_ok": (_hits(lab["issue"], str((t or {}).get("branch_issue") or "")) if lab["issue"] else None)}
        rows.append(row)
        c = by_class.setdefault(_class(lab), {"n": 0, "present": 0, "absent": 0, "wrong_fact": 0, "na": 0})
        c["n"] += 1
        if row["poisoned"]:
            c["wrong_fact"] += 1
        if row["covered"] is None:
            c["na"] += 1
        elif row["covered"]:
            c["present"] += 1
        else:
            c["absent"] += 1
    poisoned = [r for r in rows if r["poisoned"]]
    prevent_only = [r for r in rows if r["prevent_only"]]
    lost = [r for r in rows if r["covered_base_fact"] and not r["covered"]]
    new_cuts = [r for r in rows if r["caught"] and not r["caught_base"]]
    issue_bad = [r for r in new_cuts if r["issue_ok"] is False]
    # (d) prompt cost against the base run
    cost = {}
    if base:
        added_board, added_free, ms = [], [], []
        for k, r in turns.items():
            b = bturns.get(k)
            if not b or r.get("model_message") is None or b.get("model_message") is None:
                continue
            d = len(r["model_message"]) - len(b["model_message"])
            has_board = bool(r.get("fen")) or bool((r.get("board_after") or {}).get("fen"))
            (added_board if has_board else added_free).append(d)
            ms += list(r.get("facts_ms") or [])
        cost = {"board_turns": len(added_board), "median_added": pct(added_board, 0.5), "p95_added": pct(added_board, 0.95),
                "boardless_turns": len(added_free), "boardless_max_added": max(added_free) if added_free else 0,
                "provider_ms_p99": pct(ms, 0.99) if ms else None}
    return {"rows": rows, "by_class": by_class, "poisoned": len(poisoned), "poisoned_rows": [f"{r['src']}/{r['id']}" for r in poisoned],
            "prevent_only_covered": sum(1 for r in prevent_only if r["covered"]), "prevent_only": len(prevent_only),
            "prevent_only_rows": {f"{r['id']}/{r['kind']}": r["covered"] for r in prevent_only},
            "coverage_lost": [f"{r['src']}/{r['id']}/{r['kind']}" for r in lost],
            "new_cuts": len(new_cuts), "new_cut_issue_without_antidote": [f"{r['src']}/{r['id']}/{r['kind']}: {str(r['issue'])[:160]}" for r in issue_bad],
            "new_against_paired_run_only": [f"{r['src']}/{r['id']}/{r['kind']} (base cut it in {r['base_votes'][0]} of {r['base_votes'][1]} runs)"
                                            for r in rows if r["caught"] and not r["caught_base_run"] and r["caught_base"]],
            "base_runs": max((n for _, n in votes.values()), default=0),
            "cost": cost}


def gates(res: dict) -> list:
    fails = []
    a = res.get("audit")
    if a:
        if a["typed_false"] or a["typed_unproven"]:
            fails.append(f"(a) {a['typed_false']} false and {a['typed_unproven']} unproven outcome facts")
        if a["fork_bad_rate"] > 0.05:
            fails.append(f"(a) fork facts bad {a['fork_facts_bad']}/{a['fork_facts']} > 5 %")
    p = res.get("prompts")
    if p:
        if p["poisoned"]:
            fails.append(f"(b) {p['poisoned']} turns carry a fact that supports the error: {p['poisoned_rows']}")
        if p["prevent_only_covered"] < p["prevent_only"]:
            fails.append(f"(c) prevent-only rows covered {p['prevent_only_covered']}/{p['prevent_only']}")
        if p["coverage_lost"]:
            fails.append(f"(c) coverage lost against the base: {p['coverage_lost']}")
        c = p["cost"]
        if c:
            if (c["median_added"] or 0) > 600 or (c["p95_added"] or 0) > 1500:
                fails.append(f"(d) prompt cost median {c['median_added']} p95 {c['p95_added']}")
            if c["boardless_max_added"] > 0:
                fails.append(f"(d) a turn without a board got {c['boardless_max_added']} more characters")
            if c["provider_ms_p99"] is not None and c["provider_ms_p99"] > 5:
                fails.append(f"(d) provider p99 {c['provider_ms_p99']} ms")
        if p["new_cut_issue_without_antidote"]:
            fails.append(f"(e) new cuts whose issue lacks the truth: {p['new_cut_issue_without_antidote']}")
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run")
    ap.add_argument("--analysis", nargs="+", help="this run's analysis against its base run, then analyses against "
                    "further runs of the base (their base columns join the majority of (e))")
    ap.add_argument("--base-caught", default=str(FIX / "prevent" / "main_caught.json"),
                    help="the recorded baseline of (e) (default: main 02bb40d0's recorded runs; 'none' leaves it out)")
    ap.add_argument("--record-base-caught", metavar="OUT", help="write the recorded baseline from the --analysis files")
    ap.add_argument("--base-tree", help="the base tree's commit, written into --record-base-caught")
    ap.add_argument("--base-run")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--depth", type=int, default=18)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--json")
    ap.add_argument("--engine-movetime", type=int, help="the engine path's movetime (default: the turn's own)")
    a = ap.parse_args()
    global ENGINE_MOVETIME_MS
    ENGINE_MOVETIME_MS = a.engine_movetime
    os.environ.setdefault("ENGINE_API_URL", "")
    res = {}
    if a.audit:
        res["audit"] = audit(a.depth, a.limit)
        x = res["audit"]
        print(f"(a) positions {x['positions']} depth {x['depth']} ({x['seconds']} s): fork facts {x['fork_facts']}, "
              f"bad {x['fork_facts_bad']} ({x['fork_bad_rate']:.1%}); typed facts {x['typed_facts']}, "
              f"unproven {x['typed_unproven']}, false {x['typed_false']}")
        for f in x["bad_forks"][:12]:
            print(f"     bad fork {f['fork']} (loss {f['loss']}) via {f['paths']} on {f['fen']}")
    if a.record_base_caught:
        rec = record_base_caught([json.load(open(f)) for f in a.analysis or []], a.base_tree)
        json.dump(rec, open(a.record_base_caught, "w"), ensure_ascii=False, indent=1)
        print(f"recorded baseline: {len(rec['rows'])} rows cut, {rec['runs']} runs -> {a.record_base_caught}")
        return
    if a.run and a.analysis:
        run = json.load(open(a.run))
        base = json.load(open(a.base_run)) if a.base_run else None
        recorded = None
        if a.base_caught and a.base_caught != "none" and Path(a.base_caught).exists():
            recorded = json.load(open(a.base_caught))
        analyses = [json.load(open(f)) for f in a.analysis]
        res["prompts"] = p = prompts(run, analyses[0], base, analyses[1:], recorded)
        print(f"(b) poisoned prompts: {p['poisoned']} of 89 {p['poisoned_rows']}")
        print(f"(c) antidote coverage (present/absent/wrong fact/n.a.):")
        for k in sorted(p["by_class"]):
            c = p["by_class"][k]
            print(f"     {k:38} n={c['n']:3} present={c['present']:3} absent={c['absent']:3} wrong={c['wrong_fact']:2} na={c['na']}")
        print(f"    prevent-only covered {p['prevent_only_covered']}/{p['prevent_only']}: {p['prevent_only_rows']}")
        print(f"    coverage lost against the base: {p['coverage_lost'] or 'none'}")
        if p["cost"]:
            c = p["cost"]
            print(f"(d) prompt cost: board turns {c['board_turns']} median +{c['median_added']} p95 +{c['p95_added']}; "
                  f"board-less turns {c['boardless_turns']} max +{c['boardless_max_added']}; provider p99 "
                  f"{c['provider_ms_p99'] if c['provider_ms_p99'] is not None else 'n/a (no provider measured)'} ms")
        else:
            print("(d) prompt cost: no --base-run")
        print(f"(e) new cuts {p['new_cuts']} (the base by majority of {p['base_runs']} runs"
              f"{', recorded ' + str(recorded['tree']) + ' x' + str(recorded['runs']) if recorded else ''}); "
              f"without the truth in the issue: {p['new_cut_issue_without_antidote'] or 'none'}")
        if p["new_against_paired_run_only"]:
            print(f"    not new (the paired base run missed them, the base's majority cuts them): {p['new_against_paired_run_only']}")
    fails = gates(res)
    res["gate_failures"] = fails
    if a.json:
        json.dump(res, open(a.json, "w"), ensure_ascii=False, indent=1)
    if a.gate:
        print("GATE", "PASS" if not fails else "FAIL")
        for f in fails:
            print("  ", f)
        sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
