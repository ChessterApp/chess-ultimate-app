"""Summarise voice-bench runs (frontend/scripts/voice-bench.mjs) into one table.

    python scripts/voice_bench_report.py eval/bench/2026-09-24-voice [label ...]

Times are milliseconds from the end of the student's speech:
  first  — first audio of the coach (any: filler or answer)
  answer — first audio that can carry the substance: after the last response of
           an information tool (board_control only draws, so it does not count);
           equals `first` when no information tool was called
Position questions are the cases of kind "engine" / "language".
"""

import json
import sys
from pathlib import Path

DISPLAY_TOOLS = {"board_control"}


def detect_lang(text: str) -> str:
    """ru / kz / ky / en from the coach's words. ә ғ қ ұ һ і are Kazakh-only;
    ө ү ң without them is Kyrgyz (Live once answered spoken Kazakh in Kyrgyz)."""
    if not text.strip():
        return "none"
    low = text.lower()
    cyr = sum(1 for ch in low if "а" <= ch <= "я" or ch == "ё")
    lat = sum(1 for ch in low if "a" <= ch <= "z")
    if sum(low.count(ch) for ch in "әғқұһі") >= 2:
        return "kz"
    if sum(low.count(ch) for ch in "өүң") >= 2:
        return "ky"
    if cyr > lat:
        return "ru"
    return "en" if lat else "other"


def pct(values, p):
    v = sorted(x for x in values if isinstance(x, (int, float)))
    if not v:
        return None
    return v[min(len(v) - 1, int(p / 100 * len(v)))]


def answer_ms(rec):
    info = [t for t in rec.get("tools", []) if t["name"] not in DISPLAY_TOOLS]
    if not info:
        return rec.get("first_audio_ms")
    ready = max(t["at_ms"] + t["exec_ms"] for t in info)
    for seg in rec.get("segments", []):
        if seg["start"] > ready:
            return seg["start"]
    return None  # the model never spoke after the tool answered


def summarise(label, recs):
    recs = [r for r in recs if not r.get("error")]
    position = [r for r in recs if r.get("kind") in ("engine", "language")]
    answers = [answer_ms(r) for r in recs]
    pos_answers = [answer_ms(r) for r in position]
    info_calls = sum(1 for r in recs for t in r.get("tools", []) if t["name"] not in DISPLAY_TOOLS)
    engine_calls = sum(
        1 for r in recs for t in r.get("tools", []) if t["name"] in ("analyze_position", "compare_variations")
    )
    lang_ok = sum(1 for r in recs if detect_lang(r.get("model_text", "")) == r.get("expect_lang"))
    no_answer = sum(1 for a in answers if a is None)
    return {
        "label": label,
        "n": len(recs),
        "first_p50": pct([r.get("first_audio_ms") for r in recs], 50),
        "first_p90": pct([r.get("first_audio_ms") for r in recs], 90),
        "answer_p50": pct(answers, 50),
        "answer_p90": pct(answers, 90),
        "pos_answer_p50": pct(pos_answers, 50),
        "pos_answer_max": max((a for a in pos_answers if a is not None), default=None),
        "silent_over_3s": sum(1 for r in recs if (r.get("first_audio_ms") or 10**9) > 3000),
        "info_tool_calls": info_calls,
        "engine_calls": engine_calls,
        "no_answer_after_tool": no_answer,
        "lang_ok": f"{lang_ok}/{len(recs)}",
        "timeouts": sum(1 for r in recs if r.get("timeout") or r.get("closed_early")),
    }


def main():
    root = Path(sys.argv[1])
    labels = sys.argv[2:] or sorted(p.stem for p in root.glob("*.jsonl") if p.stem != "summary")
    rows = []
    for label in labels:
        path = root / f"{label}.jsonl"
        if not path.exists():
            continue
        rows.append(summarise(label, [json.loads(line) for line in path.read_text().splitlines() if line.strip()]))
    cols = list(rows[0].keys()) if rows else []
    print("| " + " | ".join(cols) + " |")
    print("|" + "---|" * len(cols))
    for row in rows:
        print("| " + " | ".join("—" if row[c] is None else str(row[c]) for c in cols) + " |")


if __name__ == "__main__":
    main()
