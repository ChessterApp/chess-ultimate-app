#!/usr/bin/env bash
# Chesster Frontend Deploy Script
# Usage: bash deploy.sh
# Builds Next.js standalone, copies assets, restarts PM2, verifies.
set -euo pipefail

FRONTEND_DIR="/root/chess-app/frontend"
STANDALONE_DIR="$FRONTEND_DIR/.next/standalone"
# Next.js standalone nests server.js under the project path relative to outputFileTracingRoot
NESTED_DIR="$STANDALONE_DIR/chess-app/frontend"

export HOME=/root

echo "=== Chesster Frontend Deploy ==="

# 1. Build
echo "[1/5] Building Next.js standalone..."
cd "$FRONTEND_DIR"
NODE_OPTIONS="--max-old-space-size=2048" npm run build

# 2. Copy static assets into standalone (nested path where server.js lives)
echo "[2/5] Copying static assets..."
cp -r .next/static "$NESTED_DIR/.next/"
cp -r public "$NESTED_DIR/"

# 2b. Inject build hash into service worker cache name
echo "[2b] Injecting build hash into sw.js..."
sed -i "s/__BUILD_HASH__/$(cat .next/BUILD_ID)/g" "$NESTED_DIR/public/sw.js"

# 3. Copy .env.local into standalone (so PM2/server.js can read it)
echo "[3/5] Copying .env.local..."
cp .env.local "$NESTED_DIR/.env.local"

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
