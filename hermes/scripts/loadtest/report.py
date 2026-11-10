"""The load test's table (how to run: scripts/loadtest/run_matrix.sh): p50/p95/max of each live-path metric per variant and N.

  python report.py results/            # every <variant>-n<N>.json in the directory
  python report.py results/ --json     # the same numbers as JSON
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import statistics


def pct(vals, p):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    k = max(0, min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1)))))
    return vals[k]


def trio(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"n": len(vals), "p50": pct(vals, 50), "p95": pct(vals, 95), "max": max(vals)}


def summarize(path: str) -> dict:
    d = json.load(open(path))
    rows, mon = d["rows"], d["monitor"]
    by = lambda k: [r for r in rows if r["kind"] == k]  # noqa: E731
    live_chat = [r for r in rows if r["kind"] in ("chat_game_question", "chat_tab_position")]
    out = {
        "to_model_live": trio([r.get("to_model") for r in live_chat]),
        "to_model_game_q": trio([r.get("to_model") for r in by("chat_game_question")]),
        "to_model_tab_pos": trio([r.get("to_model") for r in by("chat_tab_position")]),
        "answer_first_live": trio([r.get("answer_first") for r in live_chat]),
        "to_model_plan_review": trio([r.get("to_model") for r in by("chat_plan_review")]),
        "to_model_tab_review": trio([r.get("to_model") for r in by("chat_tab_review")]),
        "to_model_game_review": trio([r.get("to_model") for r in by("chat_game_review")]),
        "answer_first_plan_review": trio([r.get("answer_first") for r in by("chat_plan_review")]),
        "answer_first_tab_review": trio([r.get("answer_first") for r in by("chat_tab_review")]),
        "answer_first_game_review": trio([r.get("answer_first") for r in by("chat_game_review")]),
        "review_used": {k: f"{sum(1 for r in by(k) if r.get('review_used'))}/{len(by(k))}"
                        for k in ("chat_plan_review", "chat_tab_review", "chat_game_review")},
        "move": trio([r["ms"] for r in by("move") if not r.get("err")]),
        "voice_check": trio([r["ms"] for r in by("voice_check") if not r.get("err")]),
        "voice_over_budget": sum(1 for r in by("voice_check") if r["ms"] > 3500),
        "verify": trio([r.get("verify_ms") for r in rows if r["kind"].startswith("chat") and r.get("verify_ms")]),
        "verify_over_8s": sum(1 for r in rows if (r.get("verify_ms") or 0) > 8000),
        "comment": trio([r["ms"] for r in by("comment") if not r.get("err")]),
        "plan": trio([r["ms"] for r in by("plan")]),
        "requests": len(rows),
        "errors": [f"{r['kind']}: {r['err']}" for r in rows if r.get("err")],
    }
    pcs = [m.get("precompute") or {} for m in mon]
    pools = [m.get("pool") or {} for m in mon]
    out["precompute_max_pending"] = max((p.get("pending") or 0 for p in pcs), default=None)
    last = pcs[-1] if pcs else {}
    out["precompute_end"] = {k: last.get(k) for k in ("jobs", "steps", "cancelled", "expired", "failed", "pending",
                                                       "running")} if last else None
    lp = pools[-1] if pools else {}
    out["pool_end"] = {k: lp.get(k) for k in ("searches", "preempted", "no_time", "timeouts", "restarts")}
    out["pool_max_waiting"] = max((p.get("waiting") or 0 for p in pools), default=None)
    procs = [(m["t"], m["proc"]) for m in mon if m.get("proc")]
    cpu = []
    for (t0, a), (t1, b) in zip(procs, procs[1:]):
        if t1 > t0:
            cpu.append(100 * (b["cpu_s"] - a["cpu_s"]) / (t1 - t0) / 2)  # % of 2 vCPU
    load_end = d["wall_s"]
    t_start = procs[0][0] if procs else 0
    under_load = [c for (t, _), c in zip(procs[1:], cpu) if t - t_start <= load_end]
    out["cpu_mean_pct"] = round(statistics.mean(under_load), 1) if under_load else None
    out["cpu_max_pct"] = round(max(cpu), 1) if cpu else None
    def share(key):
        vals = []
        for (t0, a), (t1, b) in zip(procs, procs[1:]):
            if t1 > t0 and key in a and t1 - t_start <= load_end:
                vals.append(100 * (b[key] - a[key]) / (t1 - t0) / 2)
        return round(statistics.mean(vals), 1) if vals else None

    out["cpu_python_pct"] = share("py_cpu_s")
    out["cpu_stockfish_pct"] = share("stockfish_cpu_s")
    hb = [(p["host_busy_s"], p["host_total_s"]) for _, p in procs if "host_busy_s" in p]
    out["vm_busy_pct"] = round(100 * (hb[-1][0] - hb[0][0]) / max(1e-9, hb[-1][1] - hb[0][1]), 1) if len(hb) > 1 \
        else None
    rss = [p["rss_mb"] for _, p in procs]
    py = [p["py_rss_mb"] for _, p in procs]
    out["rss_mb"] = {"start": round(rss[0]), "max": round(max(rss)), "end": round(rss[-1])} if rss else None
    out["py_rss_mb"] = {"start": round(py[0]), "max": round(max(py)), "end": round(py[-1])} if py else None
    out["tail_s"] = round(d.get("tail_s") or 0, 1)
    out["wall_s"] = round(d["wall_s"])
    return out


def fmt(t):
    if not t:
        return "—"
    return f"{t['p50']}/{t['p95']}/{t['max']} (n={t['n']})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    res = {}
    for f in sorted(glob.glob(os.path.join(args.dir, "*-n*.json"))):
        m = re.match(r"(.+)-n(\d+)\.json$", os.path.basename(f))
        if m:
            res[(m.group(1), int(m.group(2)))] = summarize(f)
    if args.json:
        print(json.dumps({f"{v}-n{n}": s for (v, n), s in sorted(res.items(), key=lambda x: (x[0][1], x[0][0]))},
                         ensure_ascii=False, indent=1))
        return
    keys = ["to_model_live", "to_model_game_q", "to_model_tab_pos", "answer_first_live", "move", "voice_check",
            "voice_over_budget", "verify", "verify_over_8s", "to_model_plan_review", "to_model_tab_review",
            "to_model_game_review", "review_used", "comment", "plan", "precompute_max_pending", "precompute_end",
            "pool_max_waiting", "pool_end", "cpu_mean_pct", "cpu_max_pct", "cpu_python_pct", "cpu_stockfish_pct",
            "vm_busy_pct", "rss_mb", "py_rss_mb", "tail_s",
            "requests", "errors"]
    for n in sorted({n for _, n in res}):
        print(f"\n=== N = {n}  (ms: p50/p95/max) ===")
        vs = [v for v, nn in sorted(res) if nn == n]
        for k in keys:
            cells = []
            for v in vs:
                val = res[(v, n)].get(k)
                cells.append(fmt(val) if isinstance(val, dict) and "p50" in val else
                             (str(len(val)) + " " + "; ".join(val[:3]) if isinstance(val, list) else str(val)))
            print(f"{k:24s} " + " | ".join(f"{v}: {c}" for v, c in zip(vs, cells)))


if __name__ == "__main__":
    main()
