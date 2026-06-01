# ADR-0001: Flask backend + Next.js frontend split

- **Status:** Accepted
- **Date:** 2026-06-01 (back-dated; decision predates this ADR — written as a baseline record)
- **Deciders:** Alex
- **Tags:** `architecture, backend, frontend`

## Context

Chesster needs:

- A modern, SEO-friendly UI with SSR, complex client-side state (board, animations, Stockfish WASM, voice chat), and rapid product iteration.
- A heavy compute / data backend: native Stockfish engine, multi-agent RAG over Weaviate, 42GB TWIC SQLite, Whisper STT, vector search, long-running analysis requests.

A single Node monolith would require either (a) wrapping the native Stockfish binary in a Node child-process pool and rewriting the RAG/agent stack in JS, or (b) shelling out to Python for every analysis call. Conversely, a single Python monolith would forfeit the Next.js SSR/RSC story the frontend leans on heavily.

## Options considered

1. **All-in Next.js** — keep everything in JS, shell out to Stockfish, port RAG to JS (LangChain.js / Mastra).
   - Pros: one runtime, one deploy, single typesystem.
   - Cons: rewriting the Python ML/RAG stack; engine subprocess management in Node is brittle; loses access to the Python chess/ML ecosystem (python-chess, sentence-transformers, etc).
2. **All-in Python (FastAPI/Django + Jinja or HTMX)** — server-side rendering from Python.
   - Pros: keep ML stack native, single runtime.
   - Cons: lose Next.js's RSC + client-side interactivity story; chess UI is interactivity-heavy (drag pieces, animate, run WASM engine); poor fit.
3. **Two services: Next.js (frontend) + Flask (backend), HTTP/WebSocket between** — the chosen split.
   - Pros: each side uses its native ecosystem; clean process boundary; backend can scale independently; frontend can deploy to Vercel without dragging Python along.
   - Cons: two runtimes to operate; cross-service auth (Clerk JWT verified on both sides); duplicated type definitions; one extra network hop on every chess-data request.

## Decision

We run **Next.js 16 on port 3000** (PM2 process `chess-frontend`, standalone output) and **Flask on port 5001** (native Python venv, no Docker). They communicate over HTTP and WebSocket. Auth flows through Clerk; the frontend gets the JWT and the backend verifies it.

## Consequences

- **Positive:**
  - Backend keeps full access to Python ML/chess ecosystem (python-chess, Stockfish bindings, sentence-transformers, Weaviate client, Whisper).
  - Frontend gets full Next.js SSR/RSC + WASM Stockfish on client.
  - Each side deploys independently — frontend to Vercel as primary, VPS as fallback; backend stays on VPS where the 42GB TWIC SQLite lives.
- **Negative:**
  - Two PM2/systemd processes to monitor.
  - Clerk JWT must be verified in two places.
  - Cross-origin/CORS plumbing.
  - Latency floor: any chess-data UI render that needs backend data eats one network hop.
- **Follow-ups:**
  - Keep `frontend/.env.local` and backend env in sync for shared secrets (Clerk, Supabase).
  - Document the JWT verification flow (separate ADR if/when the auth shape changes).

## Notes

- Stack details live in `CLAUDE.md` and `ARCHITECTURE.md`.
- This ADR is a back-dated baseline — written so future ADRs that *change* this shape (e.g., moving backend off-VPS, collapsing into one runtime) have something to reference and supersede.
