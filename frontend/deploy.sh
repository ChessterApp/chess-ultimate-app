#!/usr/bin/env bash
# Chesster Frontend Deploy Script
# Usage: bash deploy.sh
# Builds Next.js standalone, copies assets, restarts PM2, verifies.
set -euo pipefail

FRONTEND_DIR="/root/chess-app/frontend"
STANDALONE_DIR="$FRONTEND_DIR/.next/standalone"
# Next.js standalone now emits a flat layout — server.js sits directly in STANDALONE_DIR.
# (Older builds nested under chess-app/frontend/; that path is gone.)
SERVER_DIR="$STANDALONE_DIR"

export HOME=/root

echo "=== Chesster Frontend Deploy ==="

# 1. Build
echo "[1/5] Building Next.js standalone..."
cd "$FRONTEND_DIR"
NODE_OPTIONS="--max-old-space-size=2048" npm run build

# Sanity check: server.js must live at the flat path.
if [ ! -f "$SERVER_DIR/server.js" ]; then
  echo "ERROR: expected $SERVER_DIR/server.js — standalone layout changed?"
  exit 1
fi

# 2. Copy static assets into standalone (flat path where server.js lives)
# Use -p to preserve mtimes so mtime-based ETags stay stable across deploys —
# otherwise the 24MB Maia model re-validates (and often re-downloads) every deploy.
echo "[2/5] Copying static assets..."
cp -rp .next/static "$SERVER_DIR/.next/"
cp -rp public "$SERVER_DIR/"

# 3. Copy .env.local into standalone (so PM2/server.js can read it)
echo "[3/5] Copying .env.local..."
cp .env.local "$SERVER_DIR/.env.local"

# 4. Restart PM2
echo "[4/5] Restarting PM2..."
PORT=3000 pm2 restart chess-frontend --update-env

# Wait for server to start
sleep 3

# 5. Verify
echo "[5/5] Verifying..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
if [ "$HTTP_CODE" = "200" ]; then
  echo "Deploy successful (HTTP $HTTP_CODE)"
else
  echo "WARNING: HTTP $HTTP_CODE — check pm2 logs chess-frontend"
  exit 1
fi
