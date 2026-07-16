# Fix Plan: Chesster Chat System — "All Response Methods Failed"

**Date:** 2026-02-08  
**Status:** 3/3 fallback layers broken  
**Severity:** Critical — no chat functionality at all

---

## Current State Diagnosis

| Layer | Route | Status | Error | Process |
|-------|-------|--------|-------|---------|
| **1. Chesster Gateway** | `chesster` / `clawdbot` keywords | ❌ BROKEN | `agentToAgent` messaging disabled | systemd `openclaw-chess.service` — running on port 19789 |
| **2. Mastra Agent** | `mastra` keywords / default | ❌ BROKEN | Frontend not running at all (PM2 empty) | PM2 `chess-frontend` — **DEAD** |
| **3. Python Backend** | last-resort fallback | ❌ BROKEN | `ECONNREFUSED 127.0.0.1:5001` | systemd `chess-backend.service` — dead since Feb 7 22:29 |

**Additional finding:** The frontend PM2 process is completely gone — not stopped, not errored, just absent. No PM2 dump exists. The entire Chesster web app is down (not just chat).

---

## Fix Order & Rationale

We fix in **reverse dependency order** — start from the deepest layer and work up:

1. **Layer 3 first** (Python backend) — zero dependencies, `systemctl start`
2. **Layer 1 second** (Chess gateway config) — needs config edit + service restart
3. **Layer 2 last** (Frontend) — depends on both Layer 1 and 3 being up; needs PM2 restart + env verification

---

## Step-by-Step Plan

### Step 1: Start Python Backend (Layer 3)

**What:** Restart the Flask backend that serves as the last-resort fallback for chat.

**Why it's safe:** 
- It's a systemd service with `Restart=always` — it just needs to be started
- It only serves HTTP on port 5001 (internal only)
- No other process uses port 5001
- The TWIC indexer is not running (stopped at 4.5%), so no SQLite lock conflict

**Commands:**
```bash
# 1. Verify port 5001 is free
ss -tlnp | grep 5001

# 2. Start the service
systemctl start chess-backend

# 3. Wait 5 seconds for Flask to initialize
sleep 5

# 4. Verify it's running
systemctl status chess-backend --no-pager | head -10
ss -tlnp | grep 5001

# 5. Health check
curl -s http://127.0.0.1:5001/api/health | head -50
```

**Rollback:** `systemctl stop chess-backend` (no state changes, pure API server)

**Risk:** ⚠️ LOW — If the TWIC indexer is ever resumed while backend is running, they'll fight over SQLite WAL lock. But indexer is stopped, so no risk now.

---

### Step 2: Fix Chess Gateway Config (Layer 1)

**What:** Enable `agentToAgent` messaging in the Chesster OpenClaw gateway config.

**Why it's broken:** The frontend calls `POST http://127.0.0.1:19789/tools/invoke` with `tool: 'sessions_send'`. The gateway rejects this because `tools.agentToAgent.enabled` defaults to `false` when not specified in the config.

**Current config:** `/root/.openclaw-chess/openclaw.json` — has a `tools` section with only `web.search`. Missing `agentToAgent` entirely.

**Fix:** Add `"agentToAgent": {"enabled": true}` to the existing `tools` object.

**Exact change to the config:**
```json
"tools": {
    "agentToAgent": {
      "enabled": true
    },
    "web": {
      "search": {
        "provider": "brave",
        "apiKey": "BSAyPqIawx_dRo-HqD5c4yQLhkd4eAf"
      }
    }
}
```

**Commands:**
```bash
# 1. Backup current config
cp /root/.openclaw-chess/openclaw.json /root/.openclaw-chess/openclaw.json.bak.20260208

# 2. Edit config (add agentToAgent to tools)
# Use jq or manual edit — add "agentToAgent": {"enabled": true} inside "tools"

# 3. Restart the chess gateway service
systemctl restart openclaw-chess

# 4. Wait for startup
sleep 10

# 5. Verify it's running on port 19789
ss -tlnp | grep 19789

# 6. Test agentToAgent is enabled
curl -s -X POST http://127.0.0.1:19789/tools/invoke \
  -H "Authorization: Bearer chesster-chess-coach-gateway-token-20260207" \
  -H "Content-Type: application/json" \
  -d '{"tool": "sessions_send", "args": {"sessionKey": "test:health", "message": "ping", "timeoutSeconds": 5}}' | head -100
# Expected: should NOT say "agentToAgent is disabled" — may get "session not found" which is fine
```

**Rollback:** `cp /root/.openclaw-chess/openclaw.json.bak.20260208 /root/.openclaw-chess/openclaw.json && systemctl restart openclaw-chess`

**Risk:** ⚠️ LOW — We're only adding one config key. The service has `Restart=always` so even if something goes wrong, systemd will recover it. Using `systemctl restart` (atomic) not stop+start (race condition — learned Jan 29).

---

### Step 3: Start Frontend & Fix Environment (Layer 2)

**What:** Restart the Next.js frontend via PM2 with correct environment variables.

**Why it's broken:** PM2 has no processes at all — the frontend was cleared from PM2's process list. The PM2 dump is empty. The web app at http://104.248.190.155 is completely down.

**The env problem:** The standalone Next.js build (`output: 'standalone'`) only bakes `NEXT_PUBLIC_*` vars at build time. Server-side vars like `CLERK_SECRET_KEY`, `OPENROUTER_API_KEY`, etc. must be available at **runtime**. The `ecosystem.config.js` solves this by reading `.env.local` and injecting vars into PM2's env. But with PM2 cleared, this was lost.

**What the ecosystem.config.js does right:**
- Reads `/root/chess-app/frontend/.env.local` at PM2 start
- Injects ALL vars (including `CLERK_SECRET_KEY`) into the process env
- Sets `PORT=3000`, `HOSTNAME=0.0.0.0`, `NODE_ENV=production`

**Commands:**
```bash
# 1. Verify no stale processes on port 3000
ss -tlnp | grep 3000

# 2. Ensure static files are linked (standalone build requires this)
cd /root/chess-app/frontend
[ -d .next/standalone/public ] || cp -r public .next/standalone/public
[ -d .next/standalone/.next/static ] || mkdir -p .next/standalone/.next && cp -r .next/static .next/standalone/.next/static

# 3. Start with ecosystem config (loads .env.local automatically)
cd /root/chess-app/frontend
pm2 start ecosystem.config.js

# 4. Verify it started
pm2 list
sleep 5

# 5. Check it's listening
ss -tlnp | grep 3000

# 6. Health check
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/

# 7. Save PM2 process list so it survives reboots
pm2 save

# 8. Verify Clerk key is loaded (check process env)
pm2 env chess-frontend 2>/dev/null | grep CLERK_SECRET_KEY | sed 's/=.*/=***/'

# 9. Test the chat endpoint
curl -s -X POST http://127.0.0.1:3000/api/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1", "query": "What is the best move?", "context_type": "position"}' \
  --max-time 10 | head -200
# Expected: Will get 401 (Unauthorized) since we're not passing Clerk token — but that proves the endpoint is alive and Clerk auth is working
```

**Rollback:** `pm2 delete chess-frontend`

**Risk:** ⚠️ MEDIUM — The main risk is the `.env.local` not being read correctly by the ecosystem config. If `CLERK_SECRET_KEY` isn't loaded, the Clerk middleware will block all authenticated routes but public routes (including `/api/*` per the middleware matcher) should still work. The chat endpoint uses `getAuth(req)` which will return null userId without Clerk, causing 401 responses.

---

### Step 4: End-to-End Verification

After all three layers are up, verify the full chat flow:

```bash
# 1. Layer 3 check — Python backend
curl -s http://127.0.0.1:5001/api/health

# 2. Layer 1 check — Chess gateway accepts sessions_send
curl -s -X POST http://127.0.0.1:19789/tools/invoke \
  -H "Authorization: Bearer chesster-chess-coach-gateway-token-20260207" \
  -H "Content-Type: application/json" \
  -d '{"tool": "sessions_send", "args": {"sessionKey": "test", "message": "hello"}}' | head -100

# 3. Layer 2 check — Frontend is serving
curl -s -o /dev/null -w "%{http_code}" http://104.248.190.155:3000/

# 4. Full flow test — open browser and try chat
# Navigate to http://104.248.190.155 → open a position → ask a question
```

---

## What This Plan Does NOT Fix (Known Issues for Later)

1. **Clerk infinite redirect loop on sign-in** — This is a pre-existing issue. The sign-in page redirects back to itself. Needs Clerk dashboard investigation (callback URL config). Not related to the chat fix.

2. **Conversation persistence (Mastra → Supabase)** — `saveConversation()` is a no-op. Mastra/Chesster chat responses are not saved. This was a known TODO before the outage.

3. **Tavily API key missing** — The Mastra agent's `searchWeb` tool will fail if invoked. Not critical — the agent can function without web search.

4. **TWIC Phase 2 indexer** — Stopped at 4.5%. Can be resumed separately once the chat system is stable. Must NOT run while `chess-backend` is active (SQLite lock conflict).

---

## Dependency Map

```
User Browser
    │
    ▼
Frontend (PM2, port 3000)  ←── Step 3
    │
    ├──[coaching keywords]──► Chess Gateway (systemd, port 19789)  ←── Step 2
    │                              │
    │                              └──► OpenClaw sessions_send → LLM response
    │
    ├──[analysis keywords]──► Mastra Agent (in-process)
    │                              │
    │                              ├──► Stockfish API (stockfish.online)
    │                              └──► LLM (OpenRouter/Gemini)
    │
    └──[last resort]────────► Python Backend (systemd, port 5001)  ←── Step 1
                                   │
                                   └──► OpenRouter → LLM response
```

No circular dependencies. Each fix is independent. Order is chosen to have maximum fallback coverage at each step.
