#!/usr/bin/env python3
"""Live model bench — the same question set through the REAL coach route on every candidate.

For each model: start Hermes on its own port with every routing tier pinned to that model
(COACH_MODEL_*), send every case of ``eval/datasets/model_bench_v1.jsonl`` to
``/api/coach/chat``, parse the SSE stream (deltas, tool_call/tool_result, usage, done) and
score the turn:

* language   — does the reply use the language of the question (ru / kk / en)
* grounding  — was an engine tool called before naming moves (ungrounded move claims = 0 is
               the bar); did the expected tool for the task get called; tool failures
* engine     — every move the reply presents is checked against Stockfish via
               ``src.eval.engine_grounded`` (illegal-move rate, cp loss), Russian notation
               (Кf3, c2-c3, 0-0) is normalised to SAN first
* speed      — time to first token, total latency, agent iterations
* cost       — USD per turn from the usage frame and ``src.model_prices``

Needs: OPENROUTER_API_KEY in hermes/.env, Stockfish (STOCKFISH_PATH), the venv python.

    python scripts/model_bench.py --models google/gemini-3.8-flash,deepseek/deepseek-v4.1-flash \
        --out eval/bench/2026-09-23 [--cases eval/datasets/model_bench_v1.jsonl] [--only ru-move-1,puzzle-2]
        [--concurrency 3] [--repeat 1] [--timeout 240]
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ENGINE_TOOLS = {"analyze_position", "compare_variations", "check_moves", "find_critical_moments"}
KK_LETTERS = set("әіңғүұқөһӘІҢҒҮҰҚӨҺ")
DEFAULT_MODELS = [
    "google/gemini-3.8-flash",
    "deepseek/deepseek-v4.1-flash",
    "deepseek/deepseek-v4-pro-0813",
    "anthropic/claude-sonnet-5",
    "moonshotai/kimi-k3",
]


# ── language ──────────────────────────────────────────────────────────────
def detect_lang(text: str) -> str:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "none"
    cyr = sum(1 for c in letters if "Ѐ" <= c <= "ӿ")
    kk = sum(1 for c in letters if c in KK_LETTERS)
    if cyr / len(letters) < 0.5:
        return "en"
    # Kazakh text uses the specific letters constantly (~1 in 12 letters); Russian never does.
    return "kk" if kk / max(cyr, 1) > 0.02 else "ru"


# ── Russian chess notation → SAN, so the engine grader can read it ────────
_RU_PIECE = {"Кр": "K", "К": "N", "С": "B", "Л": "R", "Ф": "Q"}
_RU_MOVE_RE = re.compile(r"(?<![А-Яа-яA-Za-z])(Кр|К|С|Л|Ф)(x|:)?([a-h][1-8])")
_LONG_RE = re.compile(r"\b([a-h][1-8])[-:x]([a-h][1-8])\b")
_ZERO_CASTLE_RE = re.compile(r"(?<![0-9])0-0(-0)?(?![0-9])")


def normalize_notation(text: str) -> str:
    text = _ZERO_CASTLE_RE.sub(lambda m: "O-O-O" if m.group(1) else "O-O", text)
    text = _RU_MOVE_RE.sub(lambda m: f"{_RU_PIECE[m.group(1)]}{'x' if m.group(2) else ''}{m.group(3)}", text)
    text = _LONG_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}", text)   # c2-c3 → c2c3 (UCI)
    return text


# ── one request ───────────────────────────────────────────────────────────
async def run_case(client: httpx.AsyncClient, base: str, case: dict, timeout: float) -> dict:
    body = {"message": case["message"], "locale": case.get("locale") or "ru"}
    if case.get("fen"):
        body["fen"] = case["fen"]
    text, tools, usage, error, board_actions = [], [], None, None, []
    t0 = time.monotonic()
    ttft = None
    try:
        async with client.stream("POST", f"{base}/api/coach/chat", json=body,
                                 headers={"X-User-Id": "bench"}, timeout=timeout) as r:
            if r.status_code != 200:
                error = f"http {r.status_code}: {(await r.aread())[:300]!r}"
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    d = json.loads(line[5:])
                    if "delta" in d:
                        if ttft is None and d["delta"].strip():
                            ttft = time.monotonic() - t0
                        text.append(d["delta"])
                    elif "tool_call" in d:
                        tools.append({"tool": d["tool_call"], "ok": None})
                    elif "tool_result" in d:
                        for t in reversed(tools):
                            if t["tool"] == d["tool_result"]["tool"] and t["ok"] is None:
                                t["ok"] = d["tool_result"]["ok"]
                                break
                    elif "usage" in d:
                        usage = d["usage"]
                    elif "board_actions" in d:
                        board_actions = d["board_actions"]
                    elif "error" in d:
                        error = d["error"]
    except Exception as exc:  # timeout, connection reset …
        error = f"{type(exc).__name__}: {exc}"
    total = time.monotonic() - t0
    return {
        "id": case["id"], "kind": case["kind"], "text": "".join(text), "tools": tools,
        "usage": usage, "error": error, "ttft_s": round(ttft, 2) if ttft else None,
        "total_s": round(total, 2), "board_actions": len(board_actions),
    }


# ── scoring ───────────────────────────────────────────────────────────────
def score(case: dict, res: dict, stockfish: str, depth: int) -> dict:
    from src.eval.engine_grounded import evaluate_turn
    from src.model_prices import estimate_cost_usd

    s = {}
    text = res["text"] or ""
    s["lang"] = detect_lang(text)
    s["lang_ok"] = (not res["error"]) and s["lang"] == case["expect_lang"]
    called = [t["tool"] for t in res["tools"]]
    s["tools_called"] = called
    s["tool_failures"] = [t["tool"] for t in res["tools"] if t["ok"] is False]
    s["engine_called"] = any(t in ENGINE_TOOLS for t in called)
    expect = set(case.get("expect_tools") or [])
    s["expected_tool_hit"] = (not expect) or bool(expect & set(called))

    verdict = None
    if case.get("fen") and text and not res["error"]:
        v = evaluate_turn(case["fen"], normalize_notation(text), user_text=case["message"],
                          depth=depth, stockfish_path=stockfish)
        verdict = v.to_dict()
        cued = [c for c in verdict["claims"] if c.get("kind") in ("recommended_move", "move_reference", "illegal_move")]
        s["move_claims"] = len(verdict["claims"])
        s["illegal_moves"] = [c["text"] for c in verdict["claims"] if c.get("verdict") == "illegal"]
        s["correctness"] = verdict["correctness_score"]
        s["ungrounded_move"] = bool(cued) and not s["engine_called"]
        for tag in case.get("tags", []):
            if tag.startswith("illegal:"):
                bad = tag.split(":", 1)[1]
                # the trap is caught when the reply does not present the illegal move as playable
                # (the grader flags it as illegal_move, or the reply never names it at all)
                named = [c for c in verdict["claims"] if c["text"].replace("x", "") == bad.replace("x", "")]
                s["trap_caught"] = (not named) or all(c.get("kind") == "illegal_move" for c in named)
    else:
        s["move_claims"] = 0
        s["illegal_moves"] = []
        s["correctness"] = None
        s["ungrounded_move"] = False
    s["verdict"] = verdict

    u = res.get("usage") or {}
    if u:
        s["cost_usd"] = round(estimate_cost_usd(u["model"], u["prompt_tokens"], u["completion_tokens"],
                                                u.get("cached_tokens", 0)), 5)
    else:
        s["cost_usd"] = None
    return s


# ── server lifecycle ──────────────────────────────────────────────────────
def start_server(model: str, port: int, log_path: Path) -> subprocess.Popen:
    env = dict(os.environ)
    env.update({
        "HERMES_HOME": str(ROOT / "profiles" / "chess-coach"),
        "COACH_EMIT_USAGE": "1",
        "COACH_MODEL_DEFAULT": model, "COACH_MODEL_FAST": model,
        "COACH_MODEL_ANALYSIS": model, "COACH_MODEL_DEEP": model,
    })
    env.setdefault("STOCKFISH_PATH", "/opt/homebrew/bin/stockfish")
    log = open(log_path, "w")
    return subprocess.Popen([sys.executable, "-m", "uvicorn", "src.server:app", "--port", str(port),
                             "--log-level", "warning"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


async def wait_health(base: str, seconds: int = 60) -> bool:
    async with httpx.AsyncClient() as c:
        for _ in range(seconds * 2):
            try:
                r = await c.get(f"{base}/health", timeout=2)
                if r.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


async def bench_model(model: str, cases: list, port: int, out_dir: Path, concurrency: int,
                      timeout: float, stockfish: str, depth: int, repeat: int) -> list:
    tag = model.replace("/", "__")
    proc = start_server(model, port, out_dir / f"{tag}.server.log")
    base = f"http://127.0.0.1:{port}"
    try:
        if not await wait_health(base):
            raise RuntimeError(f"{model}: server did not come up (see {tag}.server.log)")
        sem = asyncio.Semaphore(concurrency)
        results = []

        async def one(case, rep):
            async with sem:
                res = await run_case(client, base, case, timeout)
                res["rep"] = rep
                res["model"] = model
                res["score"] = score(case, res, stockfish, depth)
                results.append(res)
                mark = "ERR " if res["error"] else ("ok  " if res["score"]["lang_ok"] else "LANG")
                print(f"  {mark} {case['id']:12s} {res['total_s']:6.1f}s ttft={res['ttft_s']} "
                      f"tools={[t['tool'] for t in res['tools']]} cost={res['score']['cost_usd']}"
                      + (f"  !! {res['error'][:120]}" if res["error"] else ""), flush=True)

        async with httpx.AsyncClient() as client:
            await asyncio.gather(*(one(c, r) for r in range(repeat) for c in cases))
        results.sort(key=lambda r: (r["rep"], r["id"]))
        (out_dir / f"{tag}.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n", encoding="utf-8")
        return results
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()


# ── summary ───────────────────────────────────────────────────────────────
def summarize(all_results: dict, cases: list) -> str:
    by_id = {c["id"]: c for c in cases}
    rows = []
    for model, rs in all_results.items():
        n = len(rs)
        ok = [r for r in rs if not r["error"]]
        sc = [r["score"] for r in ok]
        graded = [r for r in ok if by_id[r["id"]].get("fen") and r["score"]["verdict"]
                  and r["score"]["verdict"]["status"] == "ok"]
        claims = sum(r["score"]["move_claims"] for r in graded)
        illegal = sum(len(r["score"]["illegal_moves"]) for r in graded)
        corr = [r["score"]["correctness"] for r in graded if r["score"]["correctness"] is not None]
        need_engine = [r for r in ok if ENGINE_TOOLS & set(by_id[r["id"]].get("expect_tools") or [])]
        lat = sorted(r["total_s"] for r in ok)
        ttft = sorted(r["ttft_s"] for r in ok if r["ttft_s"])
        cost = [r["score"]["cost_usd"] for r in ok if r["score"]["cost_usd"] is not None]
        p = lambda xs, q: (xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None)
        rows.append({
            "model": model,
            "errors": f"{n - len(ok)}/{n}",
            "lang_ok": f"{sum(1 for s in sc if s['lang_ok'])}/{len(ok)}",
            "kk_ok": f"{sum(1 for r in ok if by_id[r['id']]['expect_lang'] == 'kk' and r['score']['lang_ok'])}"
                     f"/{sum(1 for r in ok if by_id[r['id']]['expect_lang'] == 'kk')}",
            "engine_when_needed": f"{sum(1 for r in need_engine if r['score']['engine_called'])}/{len(need_engine)}",
            "expected_tool_hit": f"{sum(1 for s in sc if s['expected_tool_hit'])}/{len(ok)}",
            "ungrounded": sum(1 for s in sc if s["ungrounded_move"]),
            "tool_failures": sum(len(s["tool_failures"]) for s in sc),
            "illegal/claims": f"{illegal}/{claims}",
            "correctness": round(sum(corr) / len(corr), 2) if corr else None,
            "traps": f"{sum(1 for s in sc if s.get('trap_caught'))}/{sum(1 for s in sc if 'trap_caught' in s)}",
            "ttft_p50": p(ttft, 0.5), "total_p50": p(lat, 0.5), "total_p90": p(lat, 0.9),
            "cost_p50": round(p(cost, 0.5), 4) if cost else None,
            "cost_sum": round(sum(cost), 3) if cost else None,
            "iters_avg": round(sum((r["usage"] or {}).get("iterations") or 0 for r in ok) / max(len(ok), 1), 1),
        })
    cols = list(rows[0].keys()) if rows else []
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(DEFAULT_MODELS))
    ap.add_argument("--cases", default=str(ROOT / "eval" / "datasets" / "model_bench_v1.jsonl"))
    ap.add_argument("--only", default="")
    ap.add_argument("--skip", default="", help="comma-separated case ids to leave out")
    ap.add_argument("--out", required=True)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=240)
    ap.add_argument("--port-base", type=int, default=8660)
    ap.add_argument("--depth", type=int, default=16, help="Stockfish depth for grading")
    args = ap.parse_args()

    from src.config import load_env
    load_env()
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY missing (hermes/.env)")
    stockfish = os.environ.get("STOCKFISH_PATH") or "/opt/homebrew/bin/stockfish"
    os.environ["STOCKFISH_PATH"] = stockfish

    cases = [json.loads(l) for l in Path(args.cases).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        keep = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in keep]
    if args.skip:
        drop = set(args.skip.split(","))
        cases = [c for c in cases if c["id"] not in drop]
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    models = [m for m in args.models.split(",") if m]
    print(f"{len(cases)} cases × {len(models)} models × {args.repeat} rep → {out_dir}")

    all_results = {}
    for i, model in enumerate(models):
        print(f"\n=== {model}")
        t0 = time.time()
        all_results[model] = asyncio.run(bench_model(
            model, cases, args.port_base + i, out_dir, args.concurrency, args.timeout,
            stockfish, args.depth, args.repeat))
        print(f"  done in {time.time() - t0:.0f}s")
    table = summarize(all_results, cases)
    (out_dir / "summary.md").write_text(table + "\n", encoding="utf-8")
    print("\n" + table)


if __name__ == "__main__":
    main()
