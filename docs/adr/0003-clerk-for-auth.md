# ADR-0003: Clerk for authentication (not Supabase Auth)

- **Status:** Accepted
- **Date:** 2026-06-01 (back-dated; decision predates this ADR)
- **Deciders:** Alex
- **Tags:** `auth, frontend, backend, security`

## Context

Chesster needs user authentication that:

- Works cleanly on both sides of the Flask/Next.js split (ADR-0001) — frontend gets a session, backend verifies the same identity.
- Supports social login (Google at minimum), passwordless email, and session management without us reinventing it.
- Plugs into Next.js 16 App Router with first-class SSR/RSC support — no client-only hack.
- Doesn't lock us out of Supabase as the application database. Chesster already uses Supabase Postgres (ref `qtzujwiqzbgyhdgulvcd`) as its primary OLTP store and we don't want to give that up.

Supabase ships its own auth product (`@supabase/auth-js`), and bundling auth+DB in one vendor is tempting because RLS policies can reference `auth.uid()` directly. The counter-pressure is that Supabase Auth's Next.js story has historically been rougher than Clerk's, and our frontend leans heavily on App Router patterns.

## Options considered

1. **Clerk** — dedicated auth-as-a-service, first-class Next.js SDK, JWT-based.
   - Pros: best-in-class Next.js App Router integration (middleware, server components, `auth()` helper); polished UI components; social/passwordless/MFA out of the box; JWT is easy to verify in Flask with a JWKS endpoint.
   - Cons: another vendor and another bill; we lose the "one vendor for auth+DB" simplicity; Supabase RLS can't reference Clerk's user ID natively — we have to plumb it through (JWT template or app-level user mapping).
2. **Supabase Auth** — auth bundled with the database we already use.
   - Pros: one vendor; `auth.uid()` works directly in RLS policies; no JWT plumbing to a separate service.
   - Cons: Next.js App Router integration is rougher than Clerk's; UI components are less polished; we'd be giving up Clerk's session/MFA/orgs primitives.
3. **NextAuth.js (Auth.js)** — self-hosted, open-source.
   - Pros: no vendor; flexible; free.
   - Cons: we own everything — session storage, social provider config, breakage on Next.js upgrades; backend (Flask) JWT verification still has to be wired by hand; ops burden we don't need on a 2-person project.
4. **Roll our own (cookies + bcrypt + email magic links)** — listed for completeness.
   - Pros: full control.
   - Cons: don't.

## Decision

We use **Clerk** for authentication. Frontend uses the official Next.js SDK (Clerk middleware + `auth()` helpers). Backend (Flask) verifies Clerk-issued JWTs via Clerk's JWKS endpoint (`backend/auth.py`). Supabase is used purely as the database — its `auth.users` table is not the source of truth.

## Consequences

- **Positive:**
  - Frontend auth UI is essentially free — sign-in/sign-up/user-profile components drop in.
  - Backend JWT verification is a standard JWKS flow — no Clerk-specific lock-in at the verification layer.
  - Sessions, MFA, social providers, and (later) orgs/teams come built-in instead of being a roadmap item.
  - We can swap database vendors independently of auth, and vice versa.
- **Negative:**
  - Two vendors instead of one. Two billing relationships, two outage surfaces.
  - Supabase RLS can't use `auth.uid()` directly against Clerk identities. We either (a) carry Clerk's user ID in a JWT template Supabase trusts, or (b) enforce authorization in the Flask backend rather than RLS. Today we lean on (b) — the backend is the trust boundary, not Postgres.
  - JWT must be verified in two places (frontend middleware + backend); cache the JWKS to keep this cheap.
  - Clerk keys are environment-scoped (production/test); a leaked production key is a serious incident — keys live in `frontend/.env.local`, never committed.
- **Follow-ups:**
  - If we ever want RLS to be the trust boundary (instead of Flask), write a follow-up ADR for the Clerk-JWT-template-into-Supabase path.
  - Document the JWKS verification path in `backend/auth.py` so a future maintainer doesn't reach for the Clerk SDK and add a runtime dependency.

## Notes

- Known operational gotcha: Clerk "kid mismatch" errors on chesster.io are almost always stale browser cookies after a Clerk instance change — clearing site cookies fixes it. Captured in CLAUDE.md.
- Clerk keys in `frontend/.env.local` only. Never in source. Never in committed `.env` files.
