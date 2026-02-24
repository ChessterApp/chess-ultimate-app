#!/usr/bin/env bash
set -euo pipefail

DB_DIR="/root/chess-app/backend/data/twic"
DB_BASE="games_index.db"
DB_PATH="$DB_DIR/$DB_BASE"
AUDIT_LOG="$DB_DIR/position_db_delete_audit.log"

mkdir -p "$DB_DIR"
touch "$AUDIT_LOG"

for f in "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm" "$DB_PATH-journal"; do
  if [[ -e "$f" ]]; then
    chattr -i "$f"
  fi
done

printf '%s | user=%s | action=unprotect | target=%s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "${SUDO_USER:-$USER}" "$DB_PATH" >> "$AUDIT_LOG"
echo "Protection disabled (immutable flag removed where files exist)."
