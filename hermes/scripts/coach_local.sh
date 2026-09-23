#!/bin/sh
# Run the coach locally on ONE model (every routing tier pinned) for hand testing.
#
#   scripts/coach_local.sh deepseek/deepseek-v4.1-flash          # port 8690
#   scripts/coach_local.sh anthropic/claude-sonnet-5 8691
#
# then in another terminal:  python scripts/coach_cli.py --url http://127.0.0.1:8690
# Needs hermes/.env with OPENROUTER_API_KEY, Stockfish (brew install stockfish) and the
# venv python in $HERMES_PY (defaults to .venv/bin/python next to this repo).
set -e
MODEL="${1:?model id, e.g. google/gemini-3.8-flash}"
PORT="${2:-8690}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HERMES_PY:-$HERE/.venv/bin/python}"
[ -x "$PY" ] || { echo "python not found at $PY — set HERMES_PY=/path/to/venv/bin/python"; exit 1; }
cd "$HERE"
export HERMES_HOME="$HERE/profiles/chess-coach"
export STOCKFISH_PATH="${STOCKFISH_PATH:-$(command -v stockfish || echo /opt/homebrew/bin/stockfish)}"
export COACH_EMIT_USAGE=1
export COACH_MODEL_DEFAULT="$MODEL" COACH_MODEL_FAST="$MODEL" COACH_MODEL_ANALYSIS="$MODEL" COACH_MODEL_DEEP="$MODEL"
echo "coach on $MODEL → http://127.0.0.1:$PORT  (Ctrl-C to stop)"
exec "$PY" -m uvicorn src.server:app --port "$PORT" --log-level warning
