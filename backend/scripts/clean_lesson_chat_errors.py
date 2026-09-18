"""One-off cleanup: strip persisted error strings from lesson_chat_history.

The legacy Flask lesson-chat path used to persist the OpenRouter API error text
(e.g. "Error: OpenRouter API issue - Error code: 404 ...") as if it were the
tutor's reply. This scans every `lesson_chat_history` row, drops assistant
messages whose content is one of those error strings, and writes the cleaned
arrays back. User messages are left untouched.

Usage:
    cd /root/chess-app/backend && python scripts/clean_lesson_chat_errors.py
    # add --dry-run to report without writing.

Credentials come from the backend .env (SUPABASE_URL + SUPABASE_SERVICE_KEY).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from supabase import create_client

# Substrings that mark an assistant message as a persisted error, not a reply.
ERROR_MARKERS = (
    "Error: OpenRouter API issue",
    "Error: LLM returned no content",
    "No endpoints found",
)


def _is_error_message(msg: dict) -> bool:
    if not isinstance(msg, dict):
        return False
    if msg.get("role") != "assistant":
        return False
    content = msg.get("content") or ""
    if not isinstance(content, str):
        return False
    if content.startswith("Error:"):
        return True
    return any(marker in content for marker in ERROR_MARKERS)


def _get_supabase():
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    url = os.environ.get("SUPABASE_URL", "https://qtzujwiqzbgyhdgulvcd.supabase.co")
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if not key:
        raise ValueError("SUPABASE_SERVICE_KEY not found in environment/.env")
    return create_client(url, key)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, do not write")
    args = parser.parse_args()

    supabase = _get_supabase()

    rows = supabase.table("lesson_chat_history").select("*").execute().data or []

    rows_scanned = len(rows)
    rows_modified = 0
    messages_removed = 0

    for row in rows:
        messages = row.get("messages") or []
        if not isinstance(messages, list):
            continue
        cleaned = [m for m in messages if not _is_error_message(m)]
        removed = len(messages) - len(cleaned)
        if removed <= 0:
            continue

        messages_removed += removed
        rows_modified += 1
        print(
            f"  row user_id={row.get('user_id')} lesson_id={row.get('lesson_id')}: "
            f"removing {removed} error message(s)"
        )
        if not args.dry_run:
            supabase.table("lesson_chat_history").update(
                {"messages": cleaned}
            ).eq("user_id", row["user_id"]).eq("lesson_id", row["lesson_id"]).execute()

    mode = "DRY-RUN (no writes)" if args.dry_run else "cleaned"
    print("\n=== lesson_chat_history cleanup summary ===")
    print(f"mode:             {mode}")
    print(f"rows scanned:     {rows_scanned}")
    print(f"rows modified:    {rows_modified}")
    print(f"messages removed: {messages_removed}")


if __name__ == "__main__":
    main()
