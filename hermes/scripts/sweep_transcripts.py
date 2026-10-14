#!/usr/bin/env python3
"""sweep_transcripts — delete coach transcript files of deleted sessions.

Scans ``$HERMES_HOME/sessions`` for ``session_<id>.json`` /
``request_dump_<id>_*.json`` and removes the files of UUID session ids that
are no longer in ``coach_sessions`` (see ``src/transcript_sweep.py``).
Dry run unless ``--apply``. Prints a JSON summary; exits 1 on error.

Examples:
    python scripts/sweep_transcripts.py                 # dry run
    python scripts/sweep_transcripts.py --apply
    python scripts/sweep_transcripts.py --apply --force --max-fraction 0.9
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Make ``src`` importable whether run from the repo root or elsewhere.
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.config import PROFILE_DIR, load_env
from src.transcript_sweep import sweep


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually delete (default: dry run)")
    ap.add_argument("--force", action="store_true", help="delete even above --max-fraction")
    ap.add_argument("--max-fraction", type=float, default=0.5,
                    help="abort if orphans exceed this fraction of session ids (default 0.5)")
    ap.add_argument("--grace-min", type=float, default=60,
                    help="skip sessions with files modified in the last N minutes (default 60)")
    ap.add_argument("--dir", type=Path, default=None,
                    help="sessions dir (default: $HERMES_HOME/sessions, else the chess-coach profile)")
    args = ap.parse_args(argv)

    load_env()
    sessions_dir = args.dir or Path(os.environ.get("HERMES_HOME", str(PROFILE_DIR))) / "sessions"
    summary = sweep(
        sessions_dir,
        dry_run=not args.apply,
        force=args.force,
        max_fraction=args.max_fraction,
        grace_minutes=args.grace_min,
    )
    print(json.dumps(summary, indent=2))
    return 1 if summary["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
