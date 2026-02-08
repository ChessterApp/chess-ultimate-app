#!/bin/bash
set -a

# Load .env if it exists
[ -f .env ] && source .env

# Load .env.local if it exists (overrides .env)
[ -f .env.local ] && source .env.local

set +a

# Ensure static files are in standalone directory
if [ ! -d .next/standalone/.next/static ]; then
  echo 'Copying static files to standalone...'
  cp -r .next/static .next/standalone/.next/
  cp -r public .next/standalone/
fi

# Debug: Show loaded env vars
echo "[start.sh] CLAWDBOT_GATEWAY_TOKEN=${CLAWDBOT_GATEWAY_TOKEN:0:10}..."
echo "[start.sh] CHESSTER_GATEWAY_ENABLED=$CHESSTER_GATEWAY_ENABLED"

exec node .next/standalone/server.js
