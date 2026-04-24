#!/usr/bin/env bash
# Health check for Hermes Chess Coach service
# Usage: ./scripts/healthcheck.sh
# Exit codes: 0 = healthy, 1 = unhealthy

set -euo pipefail

PORT="${HERMES_CHESS_PORT:-8642}"
URL="http://localhost:${PORT}/health"

response=$(curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || echo "000")

if [ "$response" = "200" ]; then
    echo "OK: Hermes is healthy"
    exit 0
else
    echo "FAIL: Hermes health check returned $response"
    exit 1
fi
