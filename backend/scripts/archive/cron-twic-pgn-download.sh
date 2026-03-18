#!/bin/bash
# twic-pgn-download — Cron job: Every Monday at 09:00 UTC
# Schedule: 0 9 * * 1
#
# TASK: Download new TWIC chess game issues and append them to the master PGN file.
# DO NOT touch the SQLite database.
#
# STEPS:
# 1. Run: cd /root/chess-app/backend && python3 scripts/download_twic_updates.py
# 2. The script will automatically:
#    - Check the latest downloaded TWIC issue number
#    - Download any new issues from theweekinchess.com
#    - Append new PGN games to data/twic/twic_master_database.pgn
# 3. Report what issues were downloaded (if any) and how many games were added.
#
# FORBIDDEN ACTIONS — DO NOT DO ANY OF THESE:
# - DO NOT run index_pgn_database.py — this DESTROYS the database
# - DO NOT run add_position_index.py
# - DO NOT run any script that modifies games_index.db
# - DO NOT touch, delete, or modify any .db or .sqlite file
# - DO NOT run any Python script other than download_twic_updates.py
# - If the download script fails, just report the error. Do not improvise.
#
# This job ONLY downloads PGN files. Nothing else.

set -euo pipefail

export HOME=/root
LOGFILE="/var/log/twic-pgn-download.log"

echo "========================================" >> "$LOGFILE"
echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] twic-pgn-download starting" >> "$LOGFILE"

cd /root/chess-app/backend
python3 scripts/download_twic_updates.py >> "$LOGFILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] twic-pgn-download completed successfully" >> "$LOGFILE"
else
    echo "[$(date -u '+%Y-%m-%d %H:%M:%S UTC')] twic-pgn-download FAILED with exit code $EXIT_CODE" >> "$LOGFILE"
fi

echo "========================================" >> "$LOGFILE"
exit $EXIT_CODE
