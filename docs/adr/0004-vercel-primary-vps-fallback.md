# ADR-0004: Vercel-primary + VPS-fallback for the frontend

- **Status:** Accepted
- **Date:** 2026-06-01 (back-dated; decision predates this ADR)
- **Deciders:** Alex
- **Tags:** `deploy, frontend, ops, reliability`

## Context

The Chesster frontend (Next.js 16) needs:

- Fast global edge delivery for the marketing pages and the chess UI bundle.
- Zero-friction deploys on `main` push so iteration speed isn't bottlenecked by the VPS.
- A working fallback if Vercel has an incident or we hit a plan limit — the chess school depends on chesster.io being up during lesson hours.

The Flask backend stays on the VPS (ADR-0001) because the 42 GB TWIC SQLite (ADR-0002), Stockfish binaries, Whisper, and Weaviate client all live there and can't move to a serverless edge runtime. So the question is only about the frontend: where does Next.js run.

The VPS already has a working PM2 process (`chess-frontend`, port 3000) with the standalone Next.js output. That setup is reliable but slower to deploy (build on a 2 vCPU box takes minutes) and has no CDN — every static asset request hits the droplet directly.

## Options considered

1. **VPS-only (status quo before this ADR)** — PM2 `chess-frontend` on port 3000, Nginx in front.
   - Pros: one deploy target; full control; co-located with backend (no cross-origin within VPS).
   - Cons: no global CDN; slow builds on the 2 vCPU box; if the droplet goes down, the whole site goes down.
2. **Vercel-only** — deploy frontend to Vercel, point chesster.io DNS at Vercel.
   - Pros: edge CDN; fast iteration; preview deploys on PRs; zero ops on the frontend.
   - Cons: single point of failure on Vercel; cold-start risk for any server-rendered routes; Vercel plan limits (bandwidth, function invocations) can bite during traffic spikes.
3. **Vercel-primary + VPS-fallback (the chosen split)** — Vercel serves chesster.io; the VPS PM2 process stays warm and can take over via DNS/Cloudflare switch if Vercel is down.
   - Pros: fast everyday delivery via Vercel; documented fallback for outages; we already maintain the VPS for the backend anyway, so the fallback isn't extra ops surface.
   - Cons: two deploy targets to keep in sync; risk of drift between Vercel and VPS builds; need to keep the VPS bundle current even though most days it serves no traffic.
4. **Self-hosted CDN (Cloudflare Workers + R2 in front of VPS)** — keep ownership but add an edge.
   - Pros: no Vercel dependency.
   - Cons: significantly more wiring; we'd be rebuilding the Vercel value prop ourselves on a 2-person project.

## Decision

We deploy the frontend to **Vercel as primary** and keep the **VPS PM2 process (`chess-frontend`, port 3000) as the mirror / fallback**. Vercel auto-deploys from `main`; the VPS deploy script (`frontend/deploy.sh`) rebuilds and restarts PM2 locally — run on demand or after material changes so the fallback bundle stays current.

## Consequences

- **Positive:**
  - Production users get edge-served Next.js with CDN-cached static assets.
  - PR preview deploys come free via Vercel.
  - If Vercel has an incident or hits a plan limit, we flip DNS / Cloudflare origin to the VPS and stay up.
  - The VPS deploy is the same one we already run for the backend stack, so no new ops layer.
- **Negative:**
  - Two deploy targets. If we ship a frontend change and forget to also run `deploy.sh` on the VPS, the fallback serves a stale build during an outage.
  - Standalone output paths differ subtly per environment — past incident: PM2's `chess-frontend` standalone path is `standalone/chess-app/frontend/server.js` (nested), captured in MEMORY.md to prevent re-litigation.
  - Two billing/limit surfaces to monitor (Vercel bandwidth + VPS).
- **Follow-ups:**
  - Decide a cadence (or automate) for the VPS mirror rebuild so the fallback doesn't drift far from Vercel.
  - Document the failover steps (DNS switch, cache purge) in `memory/procedures/chesster-deploy.md` so the on-call path doesn't depend on tribal memory.
  - If Vercel costs ever outpace VPS-only, this ADR is the place to revisit and supersede.

## Notes

- The Vercel deploy is driven by `npx vercel --token $VERCEL_TOKEN` (token in CREDENTIALS.md). Vercel side is push-to-deploy from `main`.
- The VPS deploy script handles: build → copy `.next/static` and `public/` into `.next/standalone/` → `pm2 restart chess-frontend` → `curl localhost:3000` health check. Captured in CLAUDE.md.
