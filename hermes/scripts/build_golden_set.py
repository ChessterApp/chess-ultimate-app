#!/usr/bin/env python3
"""Task C — golden-set builder → eval/datasets/golden_v1.jsonl (committed, frozen).

Samples real coach turns across cohorts (rating band × message type), computes
the Task-B engine verdict once, and freezes it as ``engine_labels`` in each
golden case. The dataset file is committed and never overwritten — re-run with a
new ``--version`` to produce ``golden_v2`` later.

Source of turns (in priority order):
  1. an exported corpus dir (Task A) passed via ``--corpus`` — real traces;
  2. the committed offline fixture ``eval/fixtures/sample_corpus.jsonl``.

PII: only chess content + a coarse cohort tag are carried through. Usernames,
emails and free-form user text identifiers are never written to the golden file.

Usage:
    python scripts/build_golden_set.py                       # fixture → golden_v1
    python scripts/build_golden_set.py --corpus data/corpus/coach/v20260901
"""

import argparse
import glob
import gzip
import json
import os
import re
import sys

# Make ``src`` importable when run as a script from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.eval.engine_grounded import DEFAULT_DEPTH, evaluate_turn  # noqa: E402

FIXTURE = "eval/fixtures/sample_corpus.jsonl"
DEFAULT_OUT = "eval/datasets/golden_v1.jsonl"
# Include the whole offline fixture (58 turns) so the frozen golden set carries
# every safety case — notably the illegal-move hallucinations, which sit at the
# tail and would otherwise be dropped by a smaller per-cohort cap. Still well
# within the spec's 50–100 range.
TARGET_CASES = 58

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://\S+")


def _redact(text: str) -> str:
    """Strip emails/URLs from free text; coarse PII scrub."""
    if not text:
        return text
    text = _EMAIL_RE.sub("[email]", text)
    text = _URL_RE.sub("[url]", text)
    return text


def _load_fixture(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_corpus(corpus_dir: str) -> list[dict]:
    """Load exported corpus shards → fixture-shaped turn rows.

    A corpus record has ``fen_context``; turns without a FEN can't be engine-
    adjudicated, so they're dropped.
    """
    rows = []
    for path in sorted(glob.glob(os.path.join(corpus_dir, "shard-*.jsonl.gz"))):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                fen = rec.get("fen_context")
                if not fen or not rec.get("assistant_text"):
                    continue
                rows.append({
                    "id": f"{rec.get('session_id', 'sess')}:{rec.get('turn', '0')}",
                    "cohort": "unknown",
                    "message_type": "coach_turn",
                    "fen": fen,
                    "user_text": rec.get("user_text", ""),
                    "assistant_text": rec.get("assistant_text", ""),
                    "model": rec.get("model"),
                    "prompt_version": rec.get("prompt_version"),
                })
    return rows


def _stratified_sample(rows: list[dict], target: int) -> list[dict]:
    """Round-robin across cohorts so the sample is representative, deterministic."""
    by_cohort: dict[str, list[dict]] = {}
    for r in rows:
        by_cohort.setdefault(r.get("cohort", "unknown"), []).append(r)
    # Stable order within each cohort (by id) so the build is reproducible.
    for c in by_cohort:
        by_cohort[c].sort(key=lambda r: r.get("id", ""))

    cohorts = sorted(by_cohort)
    picked: list[dict] = []
    idxs = {c: 0 for c in cohorts}
    while len(picked) < target:
        progressed = False
        for c in cohorts:
            if idxs[c] < len(by_cohort[c]):
                picked.append(by_cohort[c][idxs[c]])
                idxs[c] += 1
                progressed = True
                if len(picked) >= target:
                    break
        if not progressed:
            break  # exhausted every cohort
    return picked


def build(rows: list[dict], depth: int, target: int) -> list[dict]:
    sample = _stratified_sample(rows, target)
    golden = []
    for r in sample:
        verdict = evaluate_turn(
            fen=r["fen"],
            assistant_text=r["assistant_text"],
            user_text=r.get("user_text", ""),
            depth=depth,
        )
        golden.append({
            "id": r["id"],
            "cohort": r.get("cohort", "unknown"),
            "message_type": r.get("message_type", "coach_turn"),
            "fen": r["fen"],
            "user_text": _redact(r.get("user_text", "")),
            "assistant_text": _redact(r["assistant_text"]),
            "model": r.get("model"),
            "prompt_version": r.get("prompt_version"),
            "engine_labels": verdict.to_dict(),
        })
    return golden


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a frozen golden set (Task C).")
    parser.add_argument("--corpus", help="Exported corpus dir (Task A). Falls back to fixture.")
    parser.add_argument("--fixture", default=FIXTURE)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH)
    parser.add_argument("--target", type=int, default=TARGET_CASES)
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite the output if it exists (default: refuse, golden sets are frozen).",
    )
    args = parser.parse_args(argv)

    if os.path.exists(args.out) and not args.force:
        print(f"Refusing to overwrite frozen dataset {args.out} (use --force or a new --out).")
        return 1

    if args.corpus and os.path.isdir(args.corpus):
        rows = _load_corpus(args.corpus)
        print(f"Loaded {len(rows)} turns from corpus {args.corpus}")
        if len(rows) < args.target:
            fixture_rows = _load_fixture(args.fixture)
            print(f"Corpus < target; topping up from fixture ({len(fixture_rows)} rows)")
            rows = rows + fixture_rows
    else:
        rows = _load_fixture(args.fixture)
        print(f"Loaded {len(rows)} turns from fixture {args.fixture}")

    golden = build(rows, args.depth, args.target)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for case in golden:
            f.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"Wrote {len(golden)} golden cases → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
