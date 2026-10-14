"""Delete on-disk coach transcripts whose session no longer exists.

The hermes-agent library writes per-session files into ``$HERMES_HOME/sessions``:

- ``session_<coach_session_id>.json`` (full transcript)
- ``request_dump_<coach_session_id>_<YYYYMMDD>_<HHMMSS>_<micro>.json``

Nothing deletes them, so when an account is deleted (``delete_user_data``
drops its ``coach_sessions`` rows) the transcripts stay behind. ``sweep``
removes the files of every UUID session id that is no longer in
``coach_sessions``; ``delete_session_files`` removes one session's files when
the user deletes it in the app.

The sweep is built to fail closed: any Supabase error or missing config
deletes nothing, an implausibly large orphan fraction (wrong DB?) aborts
unless forced, and recently modified sessions are left alone.
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path

import httpx

from src import supabase_http as _supabase_http

logger = logging.getLogger(__name__)

TIMEOUT = 10
BATCH_SIZE = 100

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
_SESSION_RE = re.compile(r"^session_(.+)\.json$")
_DUMP_RE = re.compile(r"^request_dump_(.+)_\d{8}_\d{6}_\d+\.json$")


def _sb():
    """The pooled Supabase client (src/supabase_http.py), or this module's httpx."""
    return _supabase_http.client() or httpx


def is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value or ""))


def parse_session_id(filename: str) -> str | None:
    """Session id a transcript/dump filename belongs to, or None if it is neither."""
    m = _DUMP_RE.match(filename) or _SESSION_RE.match(filename)
    return m.group(1) if m else None


def default_sessions_dir() -> Path:
    return Path(os.environ.get("HERMES_HOME", ".")) / "sessions"


def session_files(session_id: str, sessions_dir: Path) -> list[Path]:
    """All files of one session. Only UUID ids are accepted (no path traversal)."""
    if not is_uuid(session_id):
        raise ValueError(f"not a UUID session id: {session_id!r}")
    sessions_dir = Path(sessions_dir)
    candidates = [*sessions_dir.glob(f"session_{session_id}.json"),
                  *sessions_dir.glob(f"request_dump_{session_id}_*.json")]
    return [p for p in candidates if p.is_file() and parse_session_id(p.name) == session_id]


def delete_session_files(session_id: str, sessions_dir: Path | None = None) -> int:
    """Best-effort delete of one session's files. Returns how many were removed."""
    if not is_uuid(session_id):
        return 0
    deleted = 0
    try:
        for p in session_files(session_id, sessions_dir or default_sessions_dir()):
            p.unlink()
            deleted += 1
    except Exception:
        logger.warning("Failed to delete transcript files of session %s", session_id, exc_info=True)
    return deleted


def fetch_existing_ids(ids: list[str], url: str, key: str) -> set[str]:
    """Which of *ids* still exist in coach_sessions. Raises on any failure."""
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    existing: set[str] = set()
    for i in range(0, len(ids), BATCH_SIZE):
        batch = ids[i:i + BATCH_SIZE]
        resp = _sb().get(
            f"{url}/rest/v1/coach_sessions",
            params={"select": "id", "id": f"in.({','.join(batch)})"},
            headers=headers,
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        existing.update(str(row["id"]).lower() for row in resp.json())
    return existing


def sweep(
    sessions_dir: Path | None = None,
    *,
    dry_run: bool = True,
    force: bool = False,
    max_fraction: float = 0.5,
    grace_minutes: float = 60,
    url: str | None = None,
    key: str | None = None,
    now: float | None = None,
) -> dict:
    """Find (and unless *dry_run*, delete) transcript files of deleted sessions."""
    sessions_dir = Path(sessions_dir or default_sessions_dir())
    url = url if url is not None else os.environ.get("SUPABASE_URL", "")
    key = key if key is not None else os.environ.get("SUPABASE_SERVICE_KEY", "")
    now = time.time() if now is None else now
    summary = {
        "dir": str(sessions_dir),
        "dry_run": dry_run,
        "scanned": 0,
        "session_ids": 0,
        "orphans": 0,
        "orphan_ids": [],
        "deleted_files": 0,
        "bytes": 0,
        "skipped_non_uuid": [],
        "skipped_recent": 0,
        "skipped_unparsed": 0,
        "error": None,
    }
    if not url or not key:
        summary["error"] = "SUPABASE_URL / SUPABASE_SERVICE_KEY not configured"
        return summary
    if not sessions_dir.is_dir():
        summary["error"] = f"sessions dir not found: {sessions_dir}"
        return summary

    files_by_id: dict[str, list[Path]] = {}
    for p in sessions_dir.iterdir():
        if not p.is_file():
            continue
        summary["scanned"] += 1
        sid = parse_session_id(p.name)
        if sid is None:
            summary["skipped_unparsed"] += 1
        elif not is_uuid(sid):
            if sid not in summary["skipped_non_uuid"]:
                summary["skipped_non_uuid"].append(sid)
        else:
            files_by_id.setdefault(sid.lower(), []).append(p)

    # A session with any recent file may still be being created — leave it whole.
    cutoff = now - grace_minutes * 60
    candidates: dict[str, list[Path]] = {}
    for sid, paths in files_by_id.items():
        if any(p.stat().st_mtime > cutoff for p in paths):
            summary["skipped_recent"] += 1
        else:
            candidates[sid] = paths
    summary["session_ids"] = len(candidates)
    if not candidates:
        return summary

    try:
        existing = fetch_existing_ids(sorted(candidates), url, key)
    except Exception as exc:
        logger.warning("Transcript sweep: Supabase lookup failed", exc_info=True)
        summary["error"] = f"supabase lookup failed: {exc}"
        return summary

    orphans = sorted(sid for sid in candidates if sid not in existing)
    summary["orphans"] = len(orphans)
    summary["orphan_ids"] = orphans
    fraction = len(orphans) / len(candidates)
    if fraction > max_fraction and not force:
        summary["error"] = (
            f"orphan fraction {fraction:.2f} exceeds max {max_fraction:.2f}; "
            "refusing to delete (wrong database?) — rerun with force"
        )
        return summary

    for sid in orphans:
        for p in candidates[sid]:
            summary["bytes"] += p.stat().st_size
            if not dry_run:
                p.unlink()
            summary["deleted_files"] += 1
    return summary
