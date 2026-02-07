#!/bin/bash
set -a
source .env.local
set +a

# Ensure static files are in standalone directory
if [ ! -d .next/standalone/.next/static ]; then
  echo 'Copying static files to standalone...'
  cp -r .next/static .next/standalone/.next/
  cp -r public .next/standalone/
fi

exec node .next/standalone/server.js
