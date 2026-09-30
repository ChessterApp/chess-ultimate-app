#!/usr/bin/env python3
"""Grade a theory bench run (eval/datasets/theory_bench_v1.jsonl through model_bench.py).

Each case lists patterns the answer must contain (``must_any`` — one alternative
per list item) and phrases it must not (``must_not``). Also reported: time to
the first word, whole turn, how many sentences the answer check stopped, the
opening the server recognised, and the board-checkable mistakes left in the
text (src/answer_check.py run over the final answer).

    python scripts/theory_bench_report.py eval/bench/2026-09-30-theory-before eval/bench/2026-09-30-theory-after
"""
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.answer_check import CheckContext, _split_sentences, check_sentence  # noqa: E402
from src.board_markup import strip_markup  # noqa: E402

CASES = {json.loads(l)["id"]: json.loads(l) for l in open(ROOT / "eval" / "datasets" / "theory_bench_v1.jsonl")}


def grade(run_dir: Path) -> list[dict]:
    rows = []
    for path in sorted(run_dir.glob("*.jsonl")):
        for line in open(path):
            r = json.loads(line)
            case = CASES.get(r["id"])
            if not case:
                continue
            text = r.get("text") or ""
            clean, _ = strip_markup(text)
            has = all(re.search(p, clean, re.IGNORECASE) for p in case["must_any"])
            bad = [p for p in case["must_not"] if p.lower() in clean.lower()]
            ctx = CheckContext.from_fens([case["fen"]], question=case["message"])
            wrong = []
            for s in _split_sentences(clean + "\n")[0]:
                wrong += check_sentence(s, ctx)
            usage = r.get("usage") or {}
            check = usage.get("answer_check") or {}
            rows.append({
                "id": r["id"], "ok": has and not bad and not r.get("error"), "has": has, "bad": bad,
                "answer_s": r.get("answer_s"), "total_s": r.get("total_s"), "error": r.get("error"),
                "fixed": bool(check.get("fixed")), "dropped": len(check.get("dropped") or []),
                "opening": usage.get("opening"), "wrong_left": wrong, "chars": len(clean),
                "cost": (r.get("score") or {}).get("cost_usd") or r.get("cost_usd"),
            })
    return rows


def main():
    for arg in sys.argv[1:]:
        rows = grade(Path(arg))
        if not rows:
            print(arg, "— no rows")
            continue
        ans = [r["answer_s"] for r in rows if r["answer_s"]]
        tot = [r["total_s"] for r in rows if r["total_s"]]
        print(f"\n== {arg}: {sum(r['ok'] for r in rows)}/{len(rows)} answers contain what they must and nothing they must not")
        print(f"   first word p50 {statistics.median(ans):.1f} s, p90 {sorted(ans)[int(len(ans) * 0.9) - 1]:.1f} s; "
              f"whole turn p50 {statistics.median(tot):.1f} s; rewritten {sum(r['fixed'] for r in rows)}, "
              f"sentences dropped {sum(r['dropped'] for r in rows)}; board-checkable mistakes left "
              f"{sum(len(r['wrong_left']) for r in rows)}")
        for r in rows:
            mark = "ok " if r["ok"] else "BAD"
            extra = []
            if not r["has"]:
                extra.append("missing the key point")
            if r["bad"]:
                extra.append("says: " + ", ".join(r["bad"]))
            if r["wrong_left"]:
                extra.append("wrong: " + "; ".join(r["wrong_left"]))
            if r["fixed"]:
                extra.append("rewritten")
            if r["error"]:
                extra.append("error: " + str(r["error"])[:80])
            print(f"   {mark} {r['id']:<15} {r['answer_s'] or '-':>5} s  {r['opening'] or '':<45.45} {' | '.join(extra)}")


if __name__ == "__main__":
    main()
