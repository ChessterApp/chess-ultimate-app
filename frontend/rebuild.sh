#!/bin/bash
# Rebuild script for production with proper static file handling

echo 'Loading environment variables...'
export $(grep -v '^#' .env.local | grep -v '^$' | xargs)

echo 'Cleaning old build...'
rm -rf .next

echo 'Building application...'
npm run build

echo 'Copying static files to standalone...'
cp -r .next/static .next/standalone/.next/
cp -r public .next/standalone/

echo 'Restarting PM2...'
pm2 restart chess-frontend

echo 'Done! App is running.'
pm2 status
