# Architecture Decision Records (ADRs)

Short, dated records of architectural decisions made for Chesster. Each ADR captures **why** we chose a path — not what the code does (the code does that).

## Why ADRs

Agents and humans both keep asking "why is it built this way?" Code shows the *what*; PRDs show the *what we wanted*. ADRs fill the gap: **the constraints, tradeoffs, and rejected alternatives behind a decision**, so future contributors (human or AI) don't burn cycles re-litigating settled choices or accidentally reverting load-bearing ones.

## When to write an ADR

Write one when you're about to make (or just made) a decision that:

- Is **hard to reverse** later — auth provider, primary DB, language/framework choice, deployment topology.
- Has **non-obvious reasoning** — a counter-intuitive tradeoff, a workaround for a specific bug, a perf-driven shape that looks weird on the surface.
- Will **shape how others build** on top — directory conventions, error-handling pattern, data-flow contracts.
- **Locks in a constraint** — "we will never use X" or "all writes go through Y."

Skip an ADR for routine choices that any reasonable engineer would make the same way.

## How

1. Copy `0000-template.md` to `NNNN-short-title-kebab.md` (next free number, zero-padded).
2. Fill it in. Keep it short — one screen is fine, three screens is the cap.
3. Status starts as **Proposed**. After review/merge it becomes **Accepted**. If later overturned, mark **Superseded by ADR-NNNN** and add a forward link.
4. Don't edit the body of an Accepted ADR after the fact — write a new ADR that supersedes it. The history matters.

## Index

| # | Title | Status |
|---|-------|--------|
| [0001](0001-flask-nextjs-split.md) | Flask backend + Next.js frontend split | Accepted |
| [0002](0002-twic-sqlite-delete-journal-mode.md) | TWIC SQLite in DELETE journal mode (not WAL) | Accepted |
| [0003](0003-clerk-for-auth.md) | Clerk for authentication (not Supabase Auth) | Accepted |
| [0004](0004-vercel-primary-vps-fallback.md) | Vercel-primary + VPS-fallback for the frontend | Accepted |

## See also

- `ARCHITECTURE.md` — system-wide architecture overview (the *what*)
- `PRD-*.md` / `prd/` — product requirement docs (the *what we want to build*)
- `CHANGELOG.md` — release-level changes
