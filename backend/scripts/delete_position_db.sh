#!/usr/bin/env bash
set -euo pipefail

DB_DIR="/root/chess-app/backend/data/twic"
DB_BASE="games_index.db"
DB_PATH_DEFAULT="$DB_DIR/$DB_BASE"
DB_PATH="${1:-$DB_PATH_DEFAULT}"
AUDIT_LOG="$DB_DIR/position_db_delete_audit.log"

mkdir -p "$DB_DIR"
touch "$AUDIT_LOG"

prompt="Are you sure you want to delete the position database?"
echo "$prompt"
read -r answer

if [[ "$answer" != "YES" ]]; then
  printf '%s | user=%s | action=delete_aborted | target=%s | input=%q\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "${SUDO_USER:-$USER}" "$DB_PATH" "$answer" >> "$AUDIT_LOG"
  echo "Aborted. Type YES exactly to proceed."
  exit 1
fi

# Temporarily remove immutable flag from target files, then delete.
for f in "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm" "$DB_PATH-journal"; do
  if [[ -e "$f" ]]; then
    chattr -i "$f" 2>/dev/null || true
  fi
done

for f in "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm" "$DB_PATH-journal"; do
  if [[ -e "$f" ]]; then
    rm -f -- "$f"
  fi
done

printf '%s | user=%s | action=delete_confirmed_yes | target=%s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "${SUDO_USER:-$USER}" "$DB_PATH" >> "$AUDIT_LOG"
echo "Position database delete flow completed."
