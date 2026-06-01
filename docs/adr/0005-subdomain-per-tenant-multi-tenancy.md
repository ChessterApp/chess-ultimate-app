# ADR-0005: Subdomain-per-tenant with optional custom domain (multi-tenancy model)

- **Status:** Accepted
- **Date:** 2026-06-01
- **Deciders:** Alex
- **Tags:** `multi-tenancy, white-label, routing, dns, ssl`
- **Related:** ADR-0003 (Clerk), ADR-0004 (Vercel-primary)

## Context

PRD `PRD-whitelabel-ratings-calendar.md` turns Chesster into a B2B platform: each chess school is an `organization` with branded UI, isolated student/course data, and its own admin shell. Phases 1–6 + 7A/7B are code-complete on `main`; the open question is **how do tenants reach their branded experience on the network**.

Three operational pressures shape the answer:

- **Tenant onboarding has to be cheap.** Schools sign up and get a working URL the same day. Anything that requires manual per-tenant DNS/SSL plumbing won't scale past the first three customers.
- **Data isolation must be load-bearing, not cosmetic.** The PRD's `org_id` + Postgres RLS strategy only protects rows; the entry point (which org am I serving?) must be unambiguous from the URL before any query runs.
- **The PRD's original mechanism (`certbot DNS-01 + Cloudflare + Nginx wildcard on the VPS`) was written before ADR-0004.** With Vercel as primary frontend host, that runbook is stale — the chosen approach has to fit the current stack, not the 2026-04 stack.

DNS today: `chesster.io` lives on Hostinger; Vercel hosts the frontend; Vercel can issue **per-subdomain Let's Encrypt certs via HTTP-01** but cannot issue a *true wildcard* `*.chesster.io` cert without controlling the DNS zone (wildcards require DNS-01).

## Options considered

1. **Path-prefix tenancy** — `chesster.io/o/<slug>/…` for every tenant.
   - Pros: single domain, single cert, simplest routing.
   - Cons: no real white-label feel — every school sees `chesster.io` in the address bar; cookies/Clerk sessions cross-pollinate across orgs by default; harder to ever offer custom domains later without a second routing layer.
2. **Subdomain-per-tenant on `*.chesster.io`, Vercel-issued per-subdomain certs (HTTP-01)** — `school.chesster.io`, cert auto-issues on first request.
   - Pros: each school gets a branded URL with zero per-tenant infra work; cookie isolation per subdomain is free; matches Linear/Notion/Slack default; consistent with ADR-0004.
   - Cons: first hit on a new subdomain has a ~3–10 min cold-start while Let's Encrypt issues the cert; not a true wildcard (each tenant is a separate cert under the hood).
3. **Subdomain-per-tenant with a true wildcard cert (DNS-01)** — same URL shape, but one cert covers all of `*.chesster.io`.
   - Pros: zero cold-start; one cert to monitor.
   - Cons: requires moving the DNS zone to a provider Vercel can control (Vercel DNS, or Cloudflare with API creds), which would disrupt the current Hostinger setup for marginal gain.
4. **Custom domains only** — every school brings its own `chess.schoolname.com`.
   - Pros: maximum white-label.
   - Cons: blocks self-serve onboarding; requires every school to configure their own DNS before they can use the product; not a v1 default.

## Decision

**Default: subdomain-per-tenant on `*.chesster.io`, with per-subdomain SSL via Vercel's HTTP-01 issuance (option 2).**

**Upgrade: custom domain (`chess.schoolname.com`) as a paid feature**, added per-tenant via Vercel's Domains API when a school requests it. The same middleware that resolves `subdomain → org` resolves `custom-domain → org` via a `custom_domain` column on `organizations` (already in the schema).

**Data isolation:** shared Supabase Postgres, `org_id` foreign key on every tenant table, RLS policies enforce read/write boundaries (matches the migrations applied in 001 / 002 / 005).

**Auth:** Clerk Organizations (ADR-0003) provides cross-org user identity; `org_id` is injected into requests by `frontend/src/middleware.ts` based on the resolved subdomain or custom domain.

## Consequences

- **Positive:**
  - Onboarding a new school = insert a row in `organizations` with a slug; the subdomain works on first hit. No DNS, no cert, no Vercel config per tenant.
  - Subdomain cookies are scoped per tenant by browser default — no cross-org leakage from session reuse.
  - The custom-domain upgrade path is real and incremental; we don't have to build it until the first school asks.
  - Matches the prevailing B2B-SaaS pattern, which means schools' IT departments already understand it.
- **Negative:**
  - **First-hit cold start (~3–10 min)** per new subdomain while Let's Encrypt finishes HTTP-01. Mitigation: onboarding flow warms the cert by hitting the URL before handing it to the school.
  - **No true wildcard cert.** If we ever need instant subdomain provisioning at scale (50+ schools/day), we revisit by moving DNS to Vercel/Cloudflare and switching to DNS-01.
  - **Shared-DB blast radius.** One bad RLS policy can leak rows across tenants. Mitigation (follow-up): RLS test suite + cross-org fuzzer in CI before onboarding school #3.
  - The PRD's original `certbot + Nginx + Cloudflare` runbook is now stale and was amended in-place to point at Vercel instead.
- **Follow-ups:**
  - Build the **RLS test suite / cross-org fuzzer** before the third paying school. Single highest-leverage safety item.
  - Document the **custom-domain onboarding flow** (Vercel Domains API call + `organizations.custom_domain` update + verification) when the first school requests it.
  - Add a **cert-warmup step** to org creation so the school never sees the cold-start delay.
  - If we ever migrate DNS off Hostinger, this ADR is the place to revisit DNS-01 wildcard issuance.

## Notes

- Wildcard `*.chesster.io` is registered on the Vercel project `frontend` (`prj_ycg49J…`) and is verified via inheritance from the apex. The CNAME `* → cname.vercel-dns.com` lives at Hostinger.
- The middleware that does the subdomain → org lookup is `frontend/src/middleware.ts`; the org store is the `organizations` table (migration `001_organizations.sql`).
- This ADR documents the chosen approach but does **not** by itself supersede the PRD. The PRD was amended in place (§2.3, §3, §5, §10) to point at Vercel instead of certbot/Nginx; this ADR is the durable home for the *why*.
