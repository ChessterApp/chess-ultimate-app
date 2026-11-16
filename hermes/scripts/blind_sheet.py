"""Blind grading sheets for model_bench results, and the tally of the verdicts that come back.

    sheet: python scripts/blind_sheet.py sheet --cases eval/bench/<cases>.jsonl --out <dir> [--parts 6] <bench dir>...
    tally: python scripts/blind_sheet.py tally --out <dir> [--prices openrouter-models.json]

`sheet` writes <dir>/part-N.md (question, FEN, the written truth, and every answer under a number that hides
the model and the run) and <dir>/key.json. A grader fills <dir>/verdicts-N.json as {"<case>#<number>":
"ok"|"partial"|"wrong"}. Answers a model did not give itself (the turn fell to the fallback model) are left
out and counted, so a silent failover cannot be graded under the wrong name (15.11). `tally` reads the key and
every verdicts-*.json and prints, per model, the verdicts of each run, the spread between runs, the time to
the first text and the cost by the catalogue prices.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import random
import statistics
from collections import defaultdict


def _rows(bench_dirs):
    for d in bench_dirs:
        for f in sorted(glob.glob(os.path.join(d, "*__*.jsonl"))):
            for line in open(f, encoding="utf-8"):
                if line.strip():
                    yield d, json.loads(line)


def sheet(args):
    cases = {c["id"]: c for c in map(json.loads, open(args.cases, encoding="utf-8"))}
    by_case, key, dropped = defaultdict(list), {}, defaultdict(int)
    for d, r in _rows(args.bench):
        usage = r.get("usage") or {}
        if r["id"] not in cases:
            continue
        # ":online" is the same model with web search switched on for the turn, not another model.
        if (usage.get("model") or "").split(":")[0] != r["model"] or r.get("error") or not (r.get("text") or "").strip():
            dropped[r["model"]] += 1
            continue
        by_case[r["id"]].append((d, r))
    ids = sorted(by_case)
    os.makedirs(args.out, exist_ok=True)
    per = -(-len(ids) // args.parts)
    for p in range(args.parts):
        out = []
        for cid in ids[p * per:(p + 1) * per]:
            c, answers = cases[cid], by_case[cid]
            random.Random(int(hashlib.sha256(cid.encode()).hexdigest(), 16)).shuffle(answers)
            out.append(f"## {cid}\n\nВопрос: {c['message']}\n\nFEN: {c.get('fen') or 'нет'}\n\nЭТАЛОН: {c['truth']}\n")
            for n, (d, r) in enumerate(answers, 1):
                usage = r["usage"]
                key[f"{cid}#{n}"] = {
                    "model": r["model"], "run": f"{os.path.basename(os.path.normpath(d))}/{r.get('rep', 0)}",
                    "ttft_s": r.get("answer_s") or r.get("ttft_s"),
                    "prompt_tokens": usage.get("prompt_tokens", 0), "completion_tokens": usage.get("completion_tokens", 0),
                }
                out.append(f"### {cid}#{n}\n\n{r['text'].strip()}\n")
        if out:
            open(os.path.join(args.out, f"part-{p + 1}.md"), "w", encoding="utf-8").write("\n".join(out))
    json.dump(key, open(os.path.join(args.out, "key.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{len(key)} answers, {len(ids)} cases -> {args.out}")
    for m, n in sorted(dropped.items()):
        print(f"  left out (fallback model, error or empty): {m} × {n}")


def tally(args):
    key = json.load(open(os.path.join(args.out, "key.json"), encoding="utf-8"))
    verdicts = {}
    for f in sorted(glob.glob(os.path.join(args.out, "verdicts-*.json"))):
        verdicts.update(json.load(open(f, encoding="utf-8")))
    prices = {}
    if args.prices:
        for m in json.load(open(args.prices, encoding="utf-8"))["data"]:
            prices[m["id"]] = (float(m["pricing"].get("prompt") or 0), float(m["pricing"].get("completion") or 0))
    runs, times, cost, ungraded = defaultdict(lambda: defaultdict(lambda: defaultdict(int))), defaultdict(list), defaultdict(list), 0
    for label, k in key.items():
        v = verdicts.get(label)
        if v not in ("ok", "partial", "wrong"):
            ungraded += 1
            continue
        runs[k["model"]][k["run"]][v] += 1
        if k["ttft_s"] is not None:
            times[k["model"]].append(float(k["ttft_s"]))
        if k["model"] in prices:
            pin, pout = prices[k["model"]]
            cost[k["model"]].append(k["prompt_tokens"] * pin + k["completion_tokens"] * pout)
    print("| model | runs | ok per run | ok mean | wrong per run | answer starts p50 / p90, s | $ per answer |\n|---|---|---|---|---|---|---|")
    for m in sorted(runs, key=lambda m: -statistics.mean(r["ok"] for r in runs[m].values())):
        oks = [r["ok"] for _, r in sorted(runs[m].items())]
        wrongs = [r["wrong"] for _, r in sorted(runs[m].items())]
        t = sorted(times[m])
        p = (lambda q: f"{t[min(len(t) - 1, int(q * len(t)))]:.1f}") if t else (lambda q: "—")
        c = f"{statistics.mean(cost[m]):.4f}" if cost[m] else "—"
        print(f"| {m} | {len(oks)} | {' / '.join(map(str, oks))} | {statistics.mean(oks):.1f} | {' / '.join(map(str, wrongs))} | {p(0.5)} / {p(0.9)} | {c} |")
    if ungraded:
        print(f"\n{ungraded} answers have no verdict yet")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet")
    s.add_argument("--cases", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--parts", type=int, default=6)
    s.add_argument("bench", nargs="+")
    s.set_defaults(fn=sheet)
    t = sub.add_parser("tally")
    t.add_argument("--out", required=True)
    t.add_argument("--prices", default="")
    t.set_defaults(fn=tally)
    a = ap.parse_args()
    a.fn(a)
