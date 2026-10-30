#!/usr/bin/env python
"""Evaluation harness of the relation checker (plan 30.10, §5): every number split into legacy, relation, union and new.

    cd hermes
    python scripts/eval_relations.py [--parser grammar|fixture] [--judge relations|ref] [--mode off|shadow|on]
                                     [--corpus [DIR]] [--real-path [REPLAY_PY]] [--gate] [--json out.json] [-v]

Each item runs in one process with COACH_RELATION_CHECK=off (legacy) and in the requested mode (patched at runtime;
shadow and on both run, for the SHADOW == ON assertion). Sections:
  TRIAGE    45 attack-class findings of the 29.10 production runs, whole answers sentence by sentence (state carried);
            caught when a flagged sentence holds the quote. Bucket breakdown.
  NEGATIVE  48 true claims of the same answers: broken when their sentence is flagged (st2#5 whitelisted).
  EVAL      306 hand-labelled sentences (FALSE 67 / TRUE 158 / NOT-BOARD-CHECKABLE 81), ambiguous rows reported and
            not gated; by position_kind and by source.
  GRADED    the eval rows that are graded production findings.
  CORPUS    (--corpus) every coach answer of the local runs: relation flags, new versus legacy, the list to review, the
            diff against the previous run's JSON.
  LATENCY   relation_issues p50/p99/max; check_sentence p50/p99 on the fixture run and on the 500-sentence sample of
            codemap/timing.py (when its files exist).
  SHADOW    shadow records exactly the issues on returns (single sentences; whole answers up to the first relation cut).
  REAL PATH (--real-path) replay1030/replay.py (fake model, real Stockfish, async stage) off and in the mode, and the
            catch table by class in the format of analysis_final.txt (base = off, branch = the mode).
--parser fixture reads tests/fixtures/relations/recorded_claims.json instead of parsing; --judge ref judges with
tests/support/ref_judge.py (the llm design's verifier) instead of claim_scene + claim_judge. --gate reads
tests/fixtures/relations/gates.json and exits 1 on a breach.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import random
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from pathlib import Path

H = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(H))
os.chdir(H)
logging.disable(logging.WARNING)

import chess  # noqa: E402

from src import answer_check as ac  # noqa: E402
from src import answer_check_relations as acr  # noqa: E402
from src import config  # noqa: E402
from src.claim_types import Claim  # noqa: E402
from src.game_intent import spoken_squares  # noqa: E402

FIX = H / "tests" / "fixtures" / "relations"
# The local runs the corpus and the timing sample come from (outside the repository; override by flag or env).
SCRATCH = Path(os.environ.get("RELATION_SCRATCH", "/private/tmp/claude-501/-Users-asansabitov-Projects-ChessApp/"
                              "69fad51f-f89e-44e6-8aa6-5764f59ee34e/scratchpad/live1028"))
PROD_RUN = Path(os.environ.get("RELATION_PROD_RUN", str(H.parents[1] / "local-preview" / "prod-run")))

# ── the seams: the claims and the judge the relation checker uses for the item being run ──────────────────────
CUR = {"claims": [], "env": None, "text": ""}


class Recorder:
    """What relation_issues computed for each sentence (its return in on, what it recorded in shadow) and its time."""

    def __init__(self):
        self.calls: list = []
        self.times: list = []
        self.errors = 0
        self._orig = acr.relation_issues

    def install(self):
        orig = self._orig

        def wrapped(text, ctx, prior):
            before = len(ctx.relation_shadow)
            errors = ctx.relation_stats.get("errors", 0)
            t = time.perf_counter()
            out = orig(text, ctx, prior)
            dt = (time.perf_counter() - t) * 1000
            self.errors += ctx.relation_stats.get("errors", 0) - errors
            if acr.mode() != "off":
                self.times.append(dt)
            got = list(out) if out else [i for _, issues in ctx.relation_shadow[before:] for i in issues]
            self.calls.append(got)
            return out

        acr.relation_issues = wrapped


REC = Recorder()


def set_mode(mode: str) -> None:
    config.COACH_RELATION_CHECK = mode


def install_seams(parser: str, judge: str) -> None:
    if parser == "fixture":
        acr.extract_claims = lambda text, ctx, state: list(CUR["claims"])
    if judge == "ref":
        from tests.support import ref_judge

        acr.judge_claim = lambda claim, ctx, state: ref_judge.verify(claim, CUR["env"], CUR["text"])


def check(sentence: str, ctx) -> tuple:
    """(issues, relation issues, ms) of one sentence."""
    REC.calls.clear()
    t = time.perf_counter()
    issues = ac.check_sentence(sentence, ctx)
    dt = (time.perf_counter() - t) * 1000
    rel = [i for c in REC.calls for i in c]
    return issues, rel, dt


def pct(xs: list, q: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))]


# ── contexts (mirror src/server.py: the board, the shown board, the game and its line, the question, the student) ──
def make_ctx(fen, shown=None, game_moves=None, question="", student=None, puzzle_solution=None, solution_lines=None):
    color = {"w": chess.WHITE, "b": chess.BLACK}.get(student) if isinstance(student, str) else student
    lines = [" ".join(game_moves)] if game_moves else []
    ctx = ac.CheckContext.from_fens([fen, shown], lines=lines, question=question or "", student_color=color)
    if game_moves is not None:
        ctx.game_moves = list(game_moves) or None
        if game_moves and color is not None:
            first = 0 if color == chess.WHITE else 1
            ctx.game_engine_moves = [m for i, m in enumerate(game_moves) if i % 2 != first]
    if puzzle_solution:
        ctx.puzzle_solution = list(puzzle_solution)
    if solution_lines:
        ctx.solution_lines = [list(x) for x in solution_lines]
    return ctx


def ref_env(fen, shown, game_moves, student, question):
    from tests.support.ref_judge import env_for

    return env_for(fen or chess.STARTING_FEN, shown, game_moves, student, question)


# ── fixtures ────────────────────────────────────────────────────────────────────────────────────────────────────
def load(name: str) -> dict:
    return json.loads((FIX / name).read_text())


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


# ── EVAL ────────────────────────────────────────────────────────────────────────────────────────────────────────
def run_eval(rows, recorded, mode, parser, judge):
    out = []
    for row in rows:
        r = {"row": row["row"], "label": row["label"], "ambiguous": row["ambiguous"], "graded": bool(row["graded_prod_finding"]),
             "position_kind": row["position_kind"], "source": row["source"], "sentence": row["sentence"],
             "field": row["flagged_by_current_checker"]}
        sentence = spoken_squares(row["sentence"])
        CUR["claims"] = [Claim.from_dict(c) for c in recorded.get(str(row["row"]), [])] if parser == "fixture" else []
        CUR["env"] = ref_env(row["fen"], row["shown_board"], row["game_moves"], row["student"], row["question"]) if judge == "ref" else None
        CUR["text"] = (row.get("prev") or "")[-300:] + " " + row["sentence"] + " " + (row["question"] or "")
        runs = {}
        for m in (["off"] if mode == "off" else ["off", "shadow", "on"]):
            set_mode(m)
            ctx = make_ctx(row["fen"], row["shown_board"], row["game_moves"], row["question"], row["student"],
                           row.get("puzzle_solution"), row.get("solution_lines"))
            issues, rel, dt = check(sentence, ctx)
            runs[m] = {"issues": issues, "rel": rel, "ms": dt}
        r["legacy"] = bool(runs["off"]["issues"])
        r["legacy_issues"] = runs["off"]["issues"]
        mine = runs.get(mode, runs["off"])
        r["relation_issues"] = mine["rel"] if mode != "off" else []
        r["relation"] = bool(r["relation_issues"])
        r["ms"] = mine["ms"]
        r["shadow_eq_on"] = (runs["shadow"]["rel"] == runs["on"]["rel"]) if mode != "off" else True
        out.append(r)
    return out


# ── TRIAGE and NEGATIVES ──────────────────────────────────────────────────────────────────────────────────────
def frag(q: str) -> list:
    q = re.sub(r"\s+", " ", q).strip(' .…«»"')
    return [x.strip() for x in re.split(r"[…]|\.\.\.(?![A-Za-z])", q) if len(x.strip()) > 8]


def hit(quote: str, sents: list) -> list:
    fs = frag(quote)
    return [i for i, s in enumerate(sents) if any(f[:30] in re.sub(r"\s+", " ", s) for f in fs)]


def sentences(text: str) -> list:
    done, rest = ac._split_sentences((text or "") + " ")
    return [s for s in done + [rest] if s.strip()]


def run_answers(tri, recorded, eval_rows, mode, parser, judge):
    """Every answer sentence by sentence, state carried, in off / shadow / on: per answer a list of per-sentence
    results {sentence, legacy, relation, ...}."""
    by_sentence = defaultdict(list)
    for row in eval_rows:
        by_sentence[norm(row["sentence"])].append(row)
    extra = defaultdict(list)
    for x in recorded.get("triage_extra", []):
        f = next(f for f in tri["findings"] if f["id"] == x["finding"])
        extra[f["answer"]].append((x, f["quote"]))
    results, shadow_eq = {}, True
    for key, a in tri["answers"].items():
        sents = sentences(a["text"])
        claims_for = []
        for i, s in enumerate(sents):
            cl = []
            if parser == "fixture":
                rows = by_sentence.get(norm(s), [])
                row = next((r for r in rows if r["fen"] == a["fen"]), rows[0] if rows else None)
                if row is not None:
                    cl += [Claim.from_dict(c) for c in recorded["eval"].get(str(row["row"]), [])]
                for x, quote in extra.get(key, []):
                    if i in hit(quote, sents):
                        cl += [Claim.from_dict(c) for c in x["claims"]]
            claims_for.append(cl)
        env = ref_env(a["fen"], a["shown"], a["game_moves"], a["student"], a["question"]) if judge == "ref" else None
        per = {}
        for m in (["off"] if mode == "off" else ["off", "shadow", "on"]):
            set_mode(m)
            ctx = make_ctx(a["fen"] or chess.STARTING_FEN, a["shown"], a["game_moves"], a["question"], a["student"],
                           a.get("puzzle_solution"), a.get("solution_lines"))
            said = ""
            per[m] = []
            for i, s in enumerate(sents):
                CUR["claims"], CUR["env"] = claims_for[i], env
                CUR["text"] = said[-300:] + " " + s + " " + (a["question"] or "")
                issues, rel, dt = check(s, ctx)
                per[m].append({"sentence": s, "issues": issues, "rel": rel, "ms": dt})
                said += s
        if mode != "off":
            for x, y in zip(per["shadow"], per["on"]):
                if x["rel"] != y["rel"]:
                    shadow_eq = False
                if y["rel"]:
                    break  # on cut the sentence: the state of the two runs differs from here
        mine = per.get(mode, per["off"])
        results[key] = [{"sentence": s, "legacy": bool(per["off"][i]["issues"]), "legacy_issues": per["off"][i]["issues"],
                         "relation": bool(mine[i]["rel"]) if mode != "off" else False,
                         "relation_issues": mine[i]["rel"] if mode != "off" else [], "ms": mine[i]["ms"]}
                        for i, s in enumerate(sents)]
    return results, shadow_eq


def score_triage(tri, results):
    found, negs = [], []
    for f in tri["findings"]:
        out = results[f["answer"]]
        idx = hit(f["quote"], [x["sentence"] for x in out])
        leg = any(out[i]["legacy"] for i in idx)
        rel = any(out[i]["relation"] for i in idx)
        found.append({"id": f["id"], "bucket": f["check_bucket"], "quote_found": bool(idx), "legacy": leg, "relation": rel,
                      "relation_issues": [x for i in idx for x in out[i]["relation_issues"]]})
    for n in tri["negatives"]:
        out = results[n["answer"]]
        idx = hit(n["quote"], [x["sentence"] for x in out])
        negs.append({"source": n["source"], "quote": n["quote"], "quote_found": bool(idx),
                     "legacy": any(out[i]["legacy"] for i in idx), "relation": any(out[i]["relation"] for i in idx),
                     "legacy_issues": [x for i in idx for x in out[i]["legacy_issues"]][:2],
                     "relation_issues": [x for i in idx for x in out[i]["relation_issues"]][:2],
                     "whitelisted": n["source"] in tri.get("whitelist", {})})
    return found, negs


# ── CORPUS ──────────────────────────────────────────────────────────────────────────────────────────────────────
def corpus_items(L: Path):
    """The answers of fpsurface/extract.py and design-grammar/run_corpus.py: (kind, file, id, context kwargs, text)."""
    P = L / "prod1029"
    seen = set()
    pos_files = [P / "out_71.json", P / "out_30.json", P / "out_theory.json"] + \
        sorted(Path(p) for p in glob.glob(str(PROD_RUN / "out_*.json"))) + sorted(Path(p) for p in glob.glob(str(L / "stand" / "out_*.json")))
    for f in pos_files:
        try:
            o = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        for r in (o.get("rows") if isinstance(o, dict) else o) or []:
            if not (isinstance(r, dict) and r.get("fen") and r["fen"] != "@prev" and isinstance(r.get("text"), str)):
                continue
            if (r["fen"], r["text"][:200]) in seen:
                continue
            seen.add((r["fen"], r["text"][:200]))
            try:
                chess.Board(r["fen"])
            except ValueError:
                continue
            ba = r.get("boardAfter")
            if isinstance(ba, str):
                try:
                    import ast

                    ba = ast.literal_eval(ba)
                except Exception:  # noqa: BLE001
                    ba = None
            ba = ba.get("fen") if isinstance(ba, dict) else None
            yield ("pos", f.name, r.get("id"), dict(fen=r["fen"], shown=ba if ba and ba != r["fen"] else None,
                                                     question=r.get("message") or ""), r["text"])
    game_files = [L / "t1.json", L / "t2.json"] + sorted(Path(p) for p in glob.glob(str(L / "stand*" / "st*.json"))) + \
        sorted(Path(p) for p in glob.glob(str(P / "st*.json")))
    for f in game_files:
        try:
            o = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        color = None
        for stp in o.get("steps", []):
            if "said" not in stp:
                continue
            said = stp["said"]
            if re.search(r"я\s+ч[её]рн", said, re.I):
                color = "b"
            elif re.search(r"я\s+бел", said, re.I):
                color = "w"
            toks = [t for t in re.sub(r"\d+\.", " ", stp.get("notation_after") or "").split()
                    if re.match(r"^[KQRBNO]?[a-hx1-8=QRBN+#O-]+$", t)]
            b, ok = chess.Board(), []
            for t in toks:
                try:
                    b.push_san(t)
                    ok.append(t)
                except ValueError:
                    break
            for bub in (stp.get("new_bubbles") or [])[1:]:
                yield ("game", str(f.relative_to(L)), said, dict(fen=b.fen(), game_moves=ok, question=said, student=color), bub)


def corpus_split(text: str) -> list:
    done, rest = ac._split_sentences(text + " ")
    return [t for s in done + [rest] for t in re.split(r"\n+", s) if len(t.strip()) >= 4]


def run_corpus(L: Path, mode: str, parser: str, judge: str):
    flags, n, legacy_n = [], 0, 0
    for kind, fname, ident, kw, text in corpus_items(L):
        sents = [spoken_squares(s) for s in corpus_split(text)]
        env = ref_env(kw["fen"], kw.get("shown"), kw.get("game_moves"), kw.get("student"), kw.get("question")) if judge == "ref" else None
        legacy = []
        for m in ("off", mode) if mode != "off" else ("off",):
            set_mode(m)
            ctx = make_ctx(kw["fen"], kw.get("shown"), kw.get("game_moves"), kw.get("question"), kw.get("student"))
            said = ""
            for i, s in enumerate(sents):
                CUR["claims"], CUR["env"], CUR["text"] = [], env, said[-300:] + " " + s + " " + (kw.get("question") or "")
                issues, rel, _ = check(s, ctx)
                said += s
                if m == "off":
                    legacy.append(bool(issues))
                    n += 1
                    legacy_n += bool(issues)
                elif rel:
                    flags.append({"src": kind, "file": fname, "id": ident, "fen": kw["fen"], "sentence": s.strip(),
                                  "issues": rel, "legacy_flagged": legacy[i]})
    return {"sentences": n, "legacy_flagged": legacy_n, "flags": flags}


# ── LATENCY sample (codemap/timing.py) ──────────────────────────────────────────────────────────────────────────
def timing_sample(mode: str):
    files = glob.glob(str(PROD_RUN / "out_*.json")) + glob.glob(str(SCRATCH / "stand" / "out_*.json"))
    rows = []
    for f in files:
        try:
            o = json.loads(Path(f).read_text())
        except Exception:  # noqa: BLE001
            continue
        for r in (o.get("rows") if isinstance(o, dict) else o) or []:
            if isinstance(r, dict) and r.get("fen") and r.get("fen") != "@prev" and isinstance(r.get("text"), str):
                rows.append((r["fen"], r["text"], r.get("message") or ""))
    if not rows:
        return None
    random.seed(7)
    random.shuffle(rows)
    set_mode(mode)
    CUR["claims"], CUR["env"], CUR["text"] = [], None, ""
    ctx = ac.CheckContext.from_fens([rows[0][0]], question=rows[0][2])
    ac.check_sentence("Конь на f3 бьёт e5.", ctx)  # warm: imports, the book index
    times = []
    for fen, text, q in rows:
        ctx = ac.CheckContext.from_fens([fen], question=q)
        for s in re.split(r"(?<=[.!?])\s+|\n+", text):
            s = s.strip()
            if len(s) < 8:
                continue
            s = spoken_squares(s)
            t = time.perf_counter()
            ac.check_sentence(s, ctx)
            times.append((time.perf_counter() - t) * 1000)
            if len(times) >= 500:
                break
        if len(times) >= 500:
            break
    return {"n": len(times), "p50": pct(times, .5), "p99": pct(times, .99), "max": max(times)}


# ── REAL PATH ───────────────────────────────────────────────────────────────────────────────────────────────────
def real_path(replay: Path, mode: str) -> str:
    outs = {}
    tmp = Path(tempfile.mkdtemp(prefix="eval_relations_"))
    for m in ("off", mode):
        if m in outs:
            continue
        out = tmp / f"replay_{m}.json"
        env = dict(os.environ, COACH_RELATION_CHECK=m)
        with open(tmp / f"replay_{m}.log", "w") as log:
            subprocess.run([sys.executable, str(replay), str(H), str(out)], env=env, check=True, stdout=log,
                           stderr=subprocess.STDOUT)
        outs[m] = out
    analyze = replay.parent / "analyze.py"
    res = subprocess.run([sys.executable, str(analyze), str(outs["off"]), str(outs[mode])], capture_output=True, text=True,
                         check=True, cwd=str(tmp))
    return f"(base = off, branch = {mode}; files in {tmp})\n" + res.stdout


# ── GATE ────────────────────────────────────────────────────────────────────────────────────────────────────────
def gate(metrics: dict, gates: dict) -> list:
    bad = []
    for k, v in gates.get("min", {}).items():
        if k in metrics and metrics[k] < v:
            bad.append(f"{k} {metrics[k]} < {v}")
    for k, v in gates.get("max", {}).items():
        if k in metrics and metrics[k] > v:
            bad.append(f"{k} {metrics[k]} > {v}")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--parser", choices=("grammar", "fixture"), default="grammar")
    ap.add_argument("--judge", choices=("relations", "ref"), default="relations")
    ap.add_argument("--mode", choices=("off", "shadow", "on"), default="on")
    ap.add_argument("--corpus", nargs="?", const=str(SCRATCH), default=None, metavar="DIR")
    ap.add_argument("--corpus-prev", default=None, help="a previous --json output to diff the corpus flags against")
    ap.add_argument("--real-path", nargs="?", const=str(SCRATCH / "prod1029" / "replay1030" / "replay.py"), default=None,
                    metavar="REPLAY_PY")
    ap.add_argument("--no-sample", action="store_true", help="skip the 500-sentence timing sample")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--gates", default=str(FIX / "gates.json"), help="the bounds --gate reads (default: the fixture)")
    ap.add_argument("--json", default=None)
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args(argv)

    REC.install()
    install_seams(a.parser, a.judge)
    started = time.perf_counter()
    eval_fx, tri, recorded = load("eval_set.json"), load("triage.json"), load("recorded_claims.json")
    rows = eval_fx["rows"]
    print(f"mode={a.mode} parser={a.parser} judge={a.judge}")

    # warm-up (imports, the book index) so the first item's time is not the index build
    set_mode(a.mode)
    ac.check_sentence("Конь на f3 бьёт e5.", ac.CheckContext.from_fens([chess.STARTING_FEN]))
    REC.times.clear()

    m: dict = {}
    report: dict = {"mode": a.mode, "parser": a.parser, "judge": a.judge}

    # 1–2. TRIAGE, NEGATIVES
    results, sh_tri = run_answers(tri, recorded, rows, a.mode, a.parser, a.judge)
    found, negs = score_triage(tri, results)
    leg = [f["id"] for f in found if f["legacy"]]
    rel = [f["id"] for f in found if f["relation"]]
    uni = [f["id"] for f in found if f["legacy"] or f["relation"]]
    new = [f["id"] for f in found if f["relation"] and not f["legacy"]]
    m.update(triage_legacy=len(leg), triage_relation=len(rel), triage_union=len(uni), triage_new=len(new))
    print(f"TRIAGE   {len(found)} | legacy {len(leg):2d} | relation {len(rel):2d} | union {len(uni):2d} | new {len(new):2d} | "
          f"legacy {leg} new {new}")
    print("         (legacy is the sync check_sentence on whole answers; the real path adds trap-legal, cut by the engine stage)")
    nq = [f["id"] for f in found if not f["quote_found"]]
    if nq:
        print(f"         quote not found in its answer: {nq}")
    buckets = defaultdict(lambda: [0, 0, 0, 0])
    for f in found:
        b = buckets[f["bucket"]]
        b[0] += 1
        b[1] += f["legacy"]
        b[2] += f["relation"]
        b[3] += f["legacy"] or f["relation"]
    for k, (n, lg, rl, un) in sorted(buckets.items(), key=lambda x: -x[1][0]):
        print(f"  bucket {k:42s} n={n:2d} legacy {lg:2d} relation {rl:2d} union {un:2d}")
    bl = [n for n in negs if n["legacy"]]
    br = [n for n in negs if n["relation"] and not n["whitelisted"]]
    bw = [n for n in negs if n["relation"] and n["whitelisted"]]
    m.update(negatives_broken_legacy=len(bl), negatives_broken_relation=len(br))
    print(f"NEGATIVE {len(negs)} | broken legacy {len(bl)} | relation {len(br)}"
          + (f" (+{len(bw)} whitelisted: {', '.join(n['source'] for n in bw)})" if bw else " (st2#5 whitelisted)"))
    for n in bl:
        print(f"  legacy   {n['source']}: «{n['quote'][:70]}» — {(n['legacy_issues'] or [''])[0][:110]}")
    for n in br:
        print(f"  relation {n['source']}: «{n['quote'][:70]}» — {(n['relation_issues'] or [''])[0][:110]}")

    # 3–4. EVAL, GRADED
    ev = run_eval(rows, recorded["eval"], a.mode, a.parser, a.judge)
    names = {"FALSE": "FALSE", "TRUE": "TRUE ", "NOT-BOARD-CHECKABLE": "NBC  "}
    for lab in ("FALSE", "TRUE", "NOT-BOARD-CHECKABLE"):
        xs = [r for r in ev if r["label"] == lab]
        lg, rl, un = sum(r["legacy"] for r in xs), sum(r["relation"] for r in xs), sum(r["legacy"] or r["relation"] for r in xs)
        key = {"FALSE": "false", "TRUE": "true", "NOT-BOARD-CHECKABLE": "nbc"}[lab]
        g = [r for r in xs if not r["ambiguous"]]
        m.update({f"eval_{key}_legacy": lg, f"eval_{key}_relation": rl, f"eval_{key}_union": un,
                  f"eval_{key}_legacy_gated": sum(r["legacy"] for r in g), f"eval_{key}_relation_gated": sum(r["relation"] for r in g),
                  f"eval_{key}_union_gated": sum(r["legacy"] or r["relation"] for r in g)})
        print(f"EVAL {names[lab]} {len(xs):3d} | legacy {lg:2d} | relation {rl:2d} | union {un:2d} | new {sum(r['relation'] and not r['legacy'] for r in xs):2d}"
              f" || gated (non-ambiguous) {len(g)}: legacy {m[f'eval_{key}_legacy_gated']} relation {m[f'eval_{key}_relation_gated']}"
              f" union {m[f'eval_{key}_union_gated']}")
    amb = [r for r in ev if r["ambiguous"]]
    print(f"AMBIGUOUS {len(amb)} | (reported, not gated) "
          + " ".join(f"#{r['row']}:{r['label'][:1]}{'L' if r['legacy'] else ''}{'R' if r['relation'] else ''}" for r in amb))
    fld = Counter((r["label"], r["field"]) for r in ev)
    diff = [r["row"] for r in ev if r["legacy"] != r["field"]]
    print(f"  field flagged_by_current_checker: FALSE {fld[('FALSE', True)]} TRUE {fld[('TRUE', True)]} NBC "
          f"{fld[('NOT-BOARD-CHECKABLE', True)]}; legacy here differs on rows {diff}"
          + (" (the field was computed without the shown board, see eval_set.json meta)" if diff else ""))
    for dim in ("position_kind", "source"):
        tab = defaultdict(Counter)
        for r in ev:
            t = tab[r[dim]]
            t["n"] += 1
            t[r["label"]] += 1
            t[r["label"] + "L"] += r["legacy"]
            t[r["label"] + "R"] += r["relation"]
        print(f"  by {dim}: " + "; ".join(
            f"{k} n={t['n']} F {t['FALSEL']}/{t['FALSER']} of {t['FALSE']} T {t['TRUEL']}/{t['TRUER']} N {t['NOT-BOARD-CHECKABLEL']}/{t['NOT-BOARD-CHECKABLER']}"
            for k, t in sorted(tab.items(), key=lambda x: -x[1]["n"])) + "  (legacy/relation)")
    gr = [r for r in ev if r["graded"]]
    m.update(graded_legacy=sum(r["legacy"] for r in gr), graded_relation=sum(r["relation"] for r in gr),
             graded_union=sum(r["legacy"] or r["relation"] for r in gr))
    print(f"GRADED   {len(gr)} | legacy {m['graded_legacy']:2d} | relation {m['graded_relation']:2d} | union {m['graded_union']:2d}")
    if a.v:
        for r in ev:
            if r["relation"] or (r["label"] == "FALSE" and not r["legacy"]):
                print(f"  #{r['row']} {r['label'][:5]} {'L' if r['legacy'] else '-'}{'R' if r['relation'] else '-'} "
                      f"{r['sentence'][:110]}")
                for x in r["relation_issues"]:
                    print(f"        -> {x[:200]}")
        for f in found:
            for x in f["relation_issues"]:
                print(f"  triage {f['id']} -> {x[:200]}")

    # 5. CORPUS
    if a.corpus:
        cor = run_corpus(Path(a.corpus), a.mode, a.parser, a.judge)
        newf = [f for f in cor["flags"] if not f["legacy_flagged"]]
        m.update(corpus_sentences=cor["sentences"], corpus_relation_flags=len(cor["flags"]), corpus_new_flags=len(newf))
        report["corpus"] = cor
        print(f"CORPUS {cor['sentences']} sentences | legacy flagged {cor['legacy_flagged']} | relation flags {len(cor['flags'])} | "
              f"new (legacy did not flag) {len(newf)}")
        prev_path = a.corpus_prev or (a.json if a.json and Path(a.json).exists() else None)
        if prev_path:
            try:
                prev = json.loads(Path(prev_path).read_text()).get("corpus", {}).get("flags", [])
                k = lambda f: (f["file"], str(f["id"]), f["sentence"])  # noqa: E731
                was, now = {k(f) for f in prev}, {k(f) for f in cor["flags"]}
                print(f"  diff vs {prev_path}: +{len(now - was)} -{len(was - now)}")
                for x in sorted(now - was)[:40]:
                    print(f"    + {x[0]} {x[1][:30]} | {x[2][:110]}")
                for x in sorted(was - now)[:40]:
                    print(f"    - {x[0]} {x[1][:30]} | {x[2][:110]}")
            except Exception as exc:  # noqa: BLE001
                print(f"  diff vs {prev_path} failed: {exc}")
        if a.v:
            for f in cor["flags"]:
                print(f"  {'   ' if f['legacy_flagged'] else 'NEW'} {f['file']} | {f['sentence'][:120]}\n        -> {f['issues'][0][:200]}")

    # 6. LATENCY
    rt = REC.times
    m.update(relation_p99_ms=round(pct(rt, .99), 3), relation_calls=len(rt))
    cs = [r["ms"] for r in ev] + [x["ms"] for out in results.values() for x in out]
    line = (f"LATENCY relation p50 {pct(rt, .5):.3f} p99 {pct(rt, .99):.3f} max {max(rt) if rt else 0:.3f} ms ({len(rt)} calls) | "
            f"check_sentence (fixtures) p50 {pct(cs, .5):.2f} p99 {pct(cs, .99):.2f} ms")
    if not a.no_sample:
        s = timing_sample(a.mode)
        if s:
            m["check_sentence_p99_ms"] = round(s["p99"], 2)
            line += f" | sample n={s['n']} p50 {s['p50']:.2f} p99 {s['p99']:.2f} max {s['max']:.1f} ms"
    print(line)
    m["relation_errors"] = REC.errors  # fail-open: swallowed, counted on each context (ctx.relation_stats)
    if REC.errors:
        print(f"  relation errors swallowed: {REC.errors}")

    # 7. SHADOW == ON
    sh_eval = all(r["shadow_eq_on"] for r in ev)
    m["shadow_equals_on"] = int(sh_eval and sh_tri)
    print(f"SHADOW == ON: {'ok' if m['shadow_equals_on'] else 'FAILED'} (eval rows {'ok' if sh_eval else 'differ'}, "
          f"answers {'ok' if sh_tri else 'differ'})" if a.mode != "off" else "SHADOW == ON: not run (mode off)")

    # 8. REAL PATH
    if a.real_path:
        print("REAL PATH")
        print(real_path(Path(a.real_path), a.mode))

    report.update(metrics=m, triage=found, negatives=negs, eval=ev, seconds=round(time.perf_counter() - started, 1))
    rc = 0
    if a.gate:
        gates = json.loads(Path(a.gates).read_text())
        bad = gate(m, gates)
        print("GATE ok" if not bad else "GATE FAIL: " + "; ".join(bad))
        rc = 1 if bad else 0
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str))
    print(f"({report['seconds']} s)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
