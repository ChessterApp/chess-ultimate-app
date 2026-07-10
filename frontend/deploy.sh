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

# 0. Push first — chesster.io / chess-empire.chesster.io are served by VERCEL,
# which deploys from GitHub. An unpushed commit means production never changes
# no matter what this script does on the VPS. Pushing up front also lets the
# Vercel build (~2-3 min) run in parallel with the VPS build below.
AHEAD=$(cd "$FRONTEND_DIR" && git rev-list --count @{upstream}..HEAD 2>/dev/null || echo 0)
if [ "$AHEAD" -gt 0 ]; then
  echo "[0/7] Local branch is $AHEAD commit(s) ahead of origin — pushing (Vercel deploys from GitHub)..."
  if ! (cd "$FRONTEND_DIR" && git push origin HEAD); then
    echo "ERROR: git push failed. Vercel-served domains would silently keep the old"
    echo "       build. Fix the push (auth/conflict) and re-run deploy.sh."
    exit 1
  fi
else
  echo "[0/7] Branch in sync with origin — nothing to push."
fi

# 1. Build
echo "[1/7] Building Next.js standalone..."
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
echo "[2/7] Copying static assets..."
cp -rp .next/static "$SERVER_DIR/.next/"
cp -rp public "$SERVER_DIR/"

# 3. Copy .env.local into standalone (so PM2/server.js can read it)
echo "[3/7] Copying .env.local..."
cp .env.local "$SERVER_DIR/.env.local"

# 4. Restart PM2
echo "[4/7] Restarting PM2..."
PORT=3000 pm2 restart chess-frontend --update-env

# Wait for server to start
sleep 3

# 5. Verify
echo "[5/7] Verifying..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000)
if [ "$HTTP_CODE" = "200" ]; then
  echo "Deploy successful (HTTP $HTTP_CODE)"
else
  echo "WARNING: HTTP $HTTP_CODE — check pm2 logs chess-frontend"
  exit 1
fi

# 6. Verify the Maia model is served immutable — a missing 'immutable' means the
# 24MB model would re-validate/re-download on every visit (persistence regressed).
echo "[6/7] Checking Maia model cache headers..."
MODEL_URL="http://localhost:3000/maia3/maia3_simplified_int8.onnx"
CACHE_CONTROL=$(curl -sI "$MODEL_URL" | grep -i '^cache-control:' || true)
if echo "$CACHE_CONTROL" | grep -qi 'immutable'; then
  echo "Maia model cache headers OK ($CACHE_CONTROL)"
else
  echo "ERROR: Maia model is not served 'immutable' — got: '${CACHE_CONTROL:-<none>}'"
  echo "       The ~24MB model would re-download on every visit. Aborting."
  exit 1
fi

# 7. Wait for Vercel to be READY on this exact commit. The VPS above is only a
# mirror — users on chesster.io / chess-empire.chesster.io hit Vercel, so the
# deploy is not done until Vercel has built this SHA. Token lives OUTSIDE the
# repo (this file is committed) in /root/.secrets/vercel.env.
echo "[7/7] Verifying Vercel deployment..."
VERCEL_ENV_FILE="/root/.secrets/vercel.env"
if [ ! -f "$VERCEL_ENV_FILE" ]; then
  echo "ERROR: $VERCEL_ENV_FILE missing — cannot verify Vercel. Production state UNKNOWN."
  exit 1
fi
# shellcheck disable=SC1090
source "$VERCEL_ENV_FILE"
SHA=$(cd "$FRONTEND_DIR" && git rev-parse HEAD)
DEADLINE=$((SECONDS + 480))
while true; do
  STATES=$(curl -s -H "Authorization: Bearer $VERCEL_TOKEN" \
    "https://api.vercel.com/v6/deployments?limit=20" \
    | jq -r --arg sha "$SHA" '[.deployments[] | select(.meta.githubCommitSha == $sha) | .state] | join(" ")')
  if [ -n "$STATES" ]; then
    echo "  Vercel states for ${SHA:0:7}: $STATES"
    if echo "$STATES" | grep -q "ERROR"; then
      echo "ERROR: a Vercel build for $SHA failed — check the Vercel dashboard."
      exit 1
    fi
    if echo "$STATES" | grep -q "READY" && ! echo "$STATES" | grep -qE "BUILDING|QUEUED|INITIALIZING"; then
      echo "Vercel READY on $SHA — production is live."
      break
    fi
  else
    echo "  No Vercel deployment for ${SHA:0:7} yet — waiting for GitHub webhook..."
  fi
  if [ $SECONDS -ge $DEADLINE ]; then
    echo "ERROR: Vercel not READY on $SHA after 8 min. Production state UNKNOWN — do NOT report deployed."
    exit 1
  fi
  sleep 15
done
