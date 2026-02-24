#!/bin/bash
# Start chunked position indexing in background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="/tmp/twic_chunked_indexing.log"

# Run in background with nohup
cd "$SCRIPT_DIR"
nohup python3 -u index_positions_chunked.py >> "$LOG_FILE" 2>&1 &

PID=$!
echo "✓ Indexing started in background (PID: $PID)"
echo "Monitor progress: tail -f $LOG_FILE"
echo "Check status: python3 index_positions_chunked.py --status"
