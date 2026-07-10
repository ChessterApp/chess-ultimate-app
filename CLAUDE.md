# Chesster — Project Configuration

## Stack
- **Frontend:** Next.js 16, port 3000, PM2 process `chess-frontend`, standalone output
- **Backend:** Python Flask, port 5001, native venv (no Docker)
- **Auth:** Clerk (production instance, keys in `frontend/.env.local`)
- **DB:** Supabase PostgreSQL (ref: `qtzujwiqzbgyhdgulvcd`) + local SQLite for TWIC (42GB, DELETE journal mode)

## Build & Deploy
```bash
export HOME=/root && bash /root/chess-app/frontend/deploy.sh
```
`deploy.sh` does everything: **git push** (Vercel deploys from GitHub — production is Vercel, the VPS is only a mirror), build, asset copy, PM2 restart, localhost check, and **polls Vercel until READY on the exact HEAD SHA**. If it exits non-zero at the Vercel step, production state is UNKNOWN — do not report deployed.
Changes must be committed before running it (it pushes, it does not commit).
Final verification is against the real domain (`https://chesster.io` / `https://chess-empire.chesster.io`), never just localhost:3000.

## Important Rules
- **Never** modify `backend/data/twic/` files (42GB database)
- Use `NODE_OPTIONS="--max-old-space-size=2048"` for builds
- Clerk keys are in `frontend/.env.local` — never commit them
