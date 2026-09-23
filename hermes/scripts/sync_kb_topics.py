#!/usr/bin/env python3
"""Mirror hermes/content/topics/*.yaml into Supabase (kb_topics / kb_positions).

The coach does not need this — it reads the YAML. Run it so the site and the
mobile app can show the same topics. Requires migration 019 and SUPABASE_URL /
SUPABASE_SERVICE_KEY in hermes/.env. Upserts by slug; positions of a topic are
replaced wholesale. ``--dry-run`` prints what would be sent.

    python scripts/sync_kb_topics.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src import config  # noqa: E402,F401  (loads .env)
from src import knowledge_base as kb  # noqa: E402


def _rows(topics: dict) -> tuple[list[dict], list[dict]]:
    topic_rows, position_rows = [], []
    for t in topics.values():
        topic_rows.append({
            "slug": t["slug"], "phase": t["phase"], "level": t["level"],
            "title_ru": t["title_ru"], "title_kk": t["title_kk"] or None, "title_en": t["title_en"] or None,
            "summary_ru": t["summary_ru"], "summary_kk": t["summary_kk"] or None,
            "summary_en": t["summary_en"] or None,
            "key_ideas_ru": t["key_ideas_ru"], "typical_mistakes_ru": t["typical_mistakes_ru"],
            "lichess_themes": t["lichess_themes"], "eco_codes": t["eco_codes"],
            "lesson_stems": t["lesson_stems"], "related": t["related"],
            "model_games": t["model_games"], "source": t["source"],
        })
        for i, p in enumerate(t["positions"]):
            position_rows.append({
                "topic_slug": t["slug"], "ordinal": i, "title_ru": p["title_ru"],
                "title_en": p["title_en"] or None, "fen": p["fen"], "side_to_move": p["side_to_move"],
                "moves": p["moves"], "plan_ru": p["plan_ru"], "best_move": p["best_move"],
            })
    return topic_rows, position_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    topics = kb.load_topics(force=True)
    topic_rows, position_rows = _rows(topics)
    print(f"{len(topic_rows)} topics, {len(position_rows)} positions")
    if args.dry_run:
        print(json.dumps(topic_rows[0], ensure_ascii=False, indent=2)[:1200])
        return 0

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        print("SUPABASE_URL / SUPABASE_SERVICE_KEY not set", file=sys.stderr)
        return 2
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=60) as client:
        r = client.post(f"{url}/rest/v1/kb_topics", json=topic_rows,
                        headers={**headers, "Prefer": "resolution=merge-duplicates,return=minimal"})
        r.raise_for_status()
        slugs = ",".join(f'"{t["slug"]}"' for t in topic_rows)
        r = client.delete(f"{url}/rest/v1/kb_positions", params={"topic_slug": f"in.({slugs})"}, headers=headers)
        r.raise_for_status()
        if position_rows:
            r = client.post(f"{url}/rest/v1/kb_positions", json=position_rows,
                            headers={**headers, "Prefer": "return=minimal"})
            r.raise_for_status()
    print("synced")
    return 0


if __name__ == "__main__":
    sys.exit(main())
