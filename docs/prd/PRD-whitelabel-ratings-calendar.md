# PRD: White Label + Rating System + Tournament Calendar

**Version:** 1.1
**Author:** Alex + Clawdbot
**Date:** 2026-04-28 (rev. 2026-06-01)
**Status:** Draft
**Architecture reference:** `/root/clawd/notes/chesster-whitelabel-tournaments-architecture.md`
**Research basis:** `/root/clawd/memory/research/white-label-saas-multi-tenant-research.md`, `/root/clawd/memory/research/tournament-elo-rating-research.md`

### Revision Notes
- **2026-06-01 (v1.1):** Wildcard-domain mechanism updated from "certbot DNS-01 + Nginx on VPS" to "Vercel project domain + registrar wildcard CNAME". Chesster moved to Vercel-primary after this PRD was drafted (see `docs/adr/0004-vercel-primary-vps-fallback.md`). The acceptance criterion — *wildcard SSL works for any `*.chesster.io` subdomain* — is unchanged; only the execution path differs. Affected sections: §2.3, §5 Phase 1 task 7, §7 Infrastructure, §8 Modified Files.

---

## 1. Executive Summary

Three interconnected features that transform Chesster from a consumer chess learning app into a **B2B platform for chess schools**:

1. **White Label** — Partner chess schools get branded subdomains (`schoolname.chesster.io`) with isolated student data, curated content, and admin dashboards
2. **Rating System** — Single internal "Local App Rating" using the Elo formula (like Chess.com/Lichess use their own internal ratings). Updated only by offline (OTB) tournament results.
3. **Tournament Calendar** — OTB tournament listings, registration with payment, results/standings, and automatic rating updates

**Market gap:** No modern chess platform combines white-label + OTB management + a self-contained rating system. LearningChess offers a basic $50 white-label. Chess.com and ChessKid offer zero white-label. Chesster fills this gap.

**What changes:**
- New multi-tenant architecture (organizations, subdomain routing, RLS)
- New admin panel for school owners/teachers
- New tournament system with payment processing
- New internal Local App Rating engine (Elo math, no FIDE dependency, no external API calls)
- Whop integration for org billing + tournament entry fees (extending existing Whop setup)

**What doesn't change:**
- All existing features (courses, puzzles, openings, repertoire, AI coach)
- Auth provider (Clerk — using its Organizations feature)
- Database (Supabase)
- Frontend framework (Next.js 16)
- Backend (Flask)
- Free-tier individual users (chesster.io without subdomain)

---

## 2. Feature 1: White Label System

### 2.1 Multi-Tenancy Model

**Approach:** Single database, tenant-scoped via `organization_id` FK + Supabase RLS. Recommended by all major Next.js multi-tenant references (Vercel Platforms, Dub.co, SaaS-Boilerplate).

#### New Supabase Tables

```sql
-- Core tenant table
CREATE TABLE organizations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT UNIQUE NOT NULL,                 -- subdomain: slug.chesster.io
  name TEXT NOT NULL,
  logo_url TEXT,
  favicon_url TEXT,
  primary_color TEXT DEFAULT '#1a73e8',
  secondary_color TEXT DEFAULT '#ffffff',
  accent_color TEXT DEFAULT '#ffd700',
  landing_page_config JSONB DEFAULT '{}',    -- hero text, sections, CTA
  custom_css TEXT,                            -- premium: CSS overrides
  contact_email TEXT,
  status TEXT DEFAULT 'active'               -- active | suspended | trial
    CHECK (status IN ('active', 'suspended', 'trial')),
  trial_ends_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_organizations_slug ON organizations(slug);

-- Org membership + roles
CREATE TABLE organization_members (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,                     -- Clerk user ID
  role TEXT NOT NULL DEFAULT 'student'
    CHECK (role IN ('owner', 'admin', 'teacher', 'student')),
  invited_by TEXT,                           -- Clerk user ID of inviter
  invited_at TIMESTAMPTZ,
  joined_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(organization_id, user_id)
);

CREATE INDEX idx_org_members_user ON organization_members(user_id);
CREATE INDEX idx_org_members_org ON organization_members(organization_id);

-- Content curation per org
CREATE TABLE organization_content (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  course_id UUID NOT NULL,                   -- references existing courses
  visible BOOLEAN DEFAULT true,
  order_index INT DEFAULT 0,
  UNIQUE(organization_id, course_id)
);

-- Per-seat billing (Whop)
CREATE TABLE organization_billing (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  whop_membership_id TEXT,                   -- Whop membership for this org
  whop_plan_id TEXT,                         -- Whop plan ID for the tier
  plan TEXT DEFAULT 'starter'
    CHECK (plan IN ('starter', 'growth', 'enterprise')),
  student_count INT DEFAULT 0,
  price_per_student DECIMAL(10,2),
  billing_cycle TEXT DEFAULT 'monthly'
    CHECK (billing_cycle IN ('monthly', 'annual')),
  last_invoice_at TIMESTAMPTZ,
  next_invoice_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

#### Volume Pricing Tiers

| Plan | Students | Price/Student/Mo | Features |
|------|----------|------------------|----------|
| Starter | 1-99 | Base price | Subdomain, branding, content curation |
| Growth | 100-249 | Base × 0.78 | + Analytics, priority support |
| Enterprise | 250+ | Base × 0.60 | + Custom CSS, custom domain, SSO (future) |

### 2.2 Existing Table Modifications

Add nullable `organization_id UUID REFERENCES organizations(id)` to:
- `user_progress`
- `lesson_chat_history`
- `coaching_sessions`
- `user_games`
- `user_chess_profiles`

**Migration strategy:** Add column nullable → backfill NULL for existing rows (they belong to no org = direct Chesster users) → RLS policies check `organization_id IS NULL OR org membership`.

#### RLS Policy Pattern

```sql
-- Example: user_progress
CREATE POLICY "direct_user_access" ON user_progress
  USING (organization_id IS NULL AND user_id = auth.uid());

CREATE POLICY "org_member_access" ON user_progress
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_progress.organization_id
      AND om.user_id = auth.uid()
    )
  );

CREATE POLICY "org_admin_access" ON user_progress
  USING (
    organization_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM organization_members om
      WHERE om.organization_id = user_progress.organization_id
      AND om.user_id = auth.uid()
      AND om.role IN ('owner', 'admin', 'teacher')
    )
  );
```

### 2.3 Subdomain Routing

**New file: `frontend/middleware.ts`**

```
Request flow:
  almatychess.chesster.io
    → middleware extracts "almatychess" from Host header
    → lookup org by slug (cache in memory/edge, TTL 5min)
    → rewrite to /tenant/almatychess/... internally
    → set x-org-id, x-org-slug headers
    → OrganizationProvider reads headers, injects branding

  chesster.io (no subdomain)
    → normal flow, no org context
```

**Key implementation details:**
- Extract subdomain: strip `.chesster.io` from Host header
- Handle `www` → treat as main domain
- Handle `localhost:3000` for dev → use `?org=slug` query param
- Block `/admin` routes for non-admin roles
- Cache org lookup: in-memory Map with 5min TTL (edge middleware runs on every request)

**Domain / SSL (Vercel-primary):**
- Add `*.chesster.io` as a domain on the Chesster Vercel project — Vercel auto-issues a wildcard Let's Encrypt cert (covers one level only; nested `*.*.chesster.io` not covered)
- DNS: add a wildcard `CNAME * → cname.vercel-dns.com` (or A-record to Vercel anycast) at the registrar — DNS-only, not proxied
- Vercel's existing routing forwards the `Host` header to Next.js → middleware extracts the subdomain
- VPS Nginx is **not** in the request path for `*.chesster.io` (see ADR-0004 — Vercel-primary, VPS-fallback). The original PRD's certbot + Nginx mechanism was written before the Vercel migration and is superseded.

### 2.4 Branding System

**CSS Custom Properties (injected dynamically):**

```css
:root {
  --brand-primary: var(--org-primary, #1a73e8);
  --brand-secondary: var(--org-secondary, #ffffff);
  --brand-accent: var(--org-accent, #ffd700);
}
```

**New context: `frontend/src/contexts/OrganizationContext.tsx`**

```typescript
// Server: reads x-org-id header, fetches org config
// Client: provides org object (name, logo, colors, config)
// Fallback: default Chesster branding when no org
```

**Components requiring branding awareness:**
- `Navbar` — logo, school name (replaces "Chesster" text)
- `layout.tsx` — favicon, metadata title
- Landing page — hero, sections, CTA from `landing_page_config` JSONB
- Auth pages — Clerk per-org branding (logo on sign-in/sign-up)
- Footer — school info, contact

### 2.5 Admin Panel

**New routes: `/admin/*`**

| Route | Purpose | Access |
|-------|---------|--------|
| `/admin/dashboard` | Overview: students, engagement, revenue | owner, admin |
| `/admin/students` | List, invite, remove, view progress | owner, admin, teacher |
| `/admin/courses` | Toggle visibility, reorder courses | owner, admin |
| `/admin/billing` | Plan, invoices, student count, tier | owner |
| `/admin/settings` | Branding: logo, colors, landing page | owner, admin |
| `/admin/analytics` | Usage stats, completion rates, active time | owner, admin, teacher (read-only) |
| `/admin/tournaments` | Tournament management (see §4.5) | owner, admin |

**Role matrix:**
- `owner` — full access + billing + delete org
- `admin` — everything except billing/delete
- `teacher` — student management + course assignment + analytics (read-only)
- `student` — no admin access (redirected to dashboard)

### 2.6 Student Signup Flow (White Label)

1. User visits `almatychess.chesster.io/sign-up`
2. Middleware resolves org → branding applied to auth page
3. Clerk creates user
4. Clerk webhook → backend creates `organization_members` record (`role=student`)
5. User sees org-curated content only
6. A student on `schoolA.chesster.io` cannot access `schoolB.chesster.io` data

**Cross-org users:** A person can belong to multiple orgs (e.g., student at one school, teacher at another). Org context comes from the subdomain they're visiting.

### 2.7 Billing Integration

**Use Whop** for org billing — extending the existing Whop integration already in place for individual subscriptions.

- Whop Checkout for org subscription (same flow as individual plans)
- Create separate Whop plans for each org tier (Starter, Growth, Enterprise)
- Metered billing: monthly `student_count × tier_price` (tracked in our DB, Whop charges flat plan price)
- Whop webhook at `/api/whop/webhook` (already exists) handles org membership events
- Auto-tier: when student count crosses threshold, upgrade Whop plan via API next billing cycle
- Whop membership metadata stores `organization_id` for linking

**Individual plans remain on Whop** (already working — weekly/monthly/yearly).

### 2.8 Acceptance Criteria (White Label)

- [ ] School admin creates org → subdomain live within 5 minutes
- [ ] Subdomain shows school's logo, colors, name — zero Chesster branding visible
- [ ] Students on different subdomains cannot see each other's data
- [ ] Admin can invite students via email link
- [ ] Admin can toggle course visibility and reorder
- [ ] Billing page shows current plan, student count, next invoice
- [ ] Wildcard SSL cert works for any `*.chesster.io` subdomain
- [ ] PowerSync sync rules scoped by `organization_id`
- [ ] Clerk Organizations synced with Supabase `organizations` table

---

## 3. Feature 2: Rating System

### 3.1 Approach: Single Local App Rating, Elo-based, OTB-only

**One internal rating per (user, organization).** The rating is calculated by Chesster using the standard Elo formula. It is **independent** of FIDE. We do **not** fetch, store, or display official FIDE ratings — they are out of scope.

**Key design rules:**
- **Single rating per player.** No time-control pools (no separate Standard/Rapid/Blitz). Like a local club rating.
- **Updated only by offline (OTB) tournaments.** Online games, puzzle results, course completion, etc. do **not** affect the rating.
- **Rating only updates when** the tournament is finalized AND `is_rated = true` AND `tournament_mode = 'offline'`. Unrated tournaments and online events leave the rating untouched.
- **Elo formula** (industry-standard, same math as FIDE/USCF/Chess.com/Lichess use as their core engine, but the **rating pool is local** to Chesster — every org has its own rating pool).

**Why this shape:**
- The product is OTB-focused (school tournaments, club events, scholastic competitions). A single rating is what arbiters, coaches, and parents already understand.
- Online events are explicitly out of scope for v1 (PRD §4.6 places them in v2). Excluding them from the rating system means we never have to reason about cheating, lag, or platform integrity.
- Elo is the simplest, well-understood, no-tuning-needed algorithm.

### 3.2 Database Schema

```sql
-- Player rating: single rating per user per organization
CREATE TABLE player_ratings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  organization_id UUID REFERENCES organizations(id),
  rating INT DEFAULT 1200,
  peak_rating INT DEFAULT 1200,
  k_factor INT DEFAULT 40,                     -- see K-factor rules below
  games_played INT DEFAULT 0,                  -- counts only rated OTB games
  wins INT DEFAULT 0,
  draws INT DEFAULT 0,
  losses INT DEFAULT 0,
  league TEXT DEFAULT 'C'
    CHECK (league IN ('C', 'B', 'A', 'Master')),
  is_provisional BOOLEAN DEFAULT true,         -- true when games_played < 30
  last_game_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(user_id, organization_id)
);

-- Every rating change logged. Source is always a finalized rated OTB tournament.
CREATE TABLE rating_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'tournament'
    CHECK (source_type IN ('tournament')),     -- only OTB tournaments produce rating events
  source_id UUID,                              -- tournament_id
  rating_before INT NOT NULL,
  rating_after INT NOT NULL,
  change INT NOT NULL,
  k_factor_used INT NOT NULL,
  calculated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_rating_history_user ON rating_history(user_id, calculated_at);
```

**Removed from earlier draft:** `player_fide_ratings` table and all FIDE ID linkage. Chesster does not store FIDE IDs or official FIDE ratings.

### 3.3 Elo Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Starting rating | 1200 | Lower than FIDE/USCF defaults (1400/1200) — target is children/beginners |
| K-factor (provisional, <30 games) | 40 | Fast convergence for new players |
| K-factor (rating < 2300) | 20 | Standard adult/serious-player K |
| K-factor (rating ≥ 2300) | 10 | Stability for top-tier players |
| Provisional threshold | < 30 games | Industry-standard definition |
| Rating floor | 800 | Prevents discouraging sub-1000 drops for children |
| Rated game source | Finalized rated OTB tournaments only | Online play, puzzles, courses do not affect rating |

**Elo formula:**
- Expected score: `E = 1 / (1 + 10^((Ro - Rp) / 400))`
- New rating: `R' = R + K × (S - E)` where S = actual score (1, 0.5, 0)

These are the same equations FIDE/USCF/Chess.com/Lichess use as their core engine. Chesster runs them against its **own** local rating pool — there is no FIDE rating fetching or syncing.

### 3.4 League System

| League | Rating Range | Badge | Color |
|--------|-------------|-------|-------|
| C | < 1400 | Bronze | `#cd7f32` |
| B | 1400-1799 | Silver | `#c0c0c0` |
| A | 1800-2199 | Gold | `#ffd700` |
| Master | 2200+ | Diamond | `#b9f2ff` |

**League assignment:** Based on current rating after each game. Simple threshold — no hysteresis needed since K-factors already smooth the transitions. Provisional players (< 30 games) show "Unrated" badge.

### 3.5 Rating API Endpoints

```
GET  /api/ratings/:userId              — Player's Local App Rating
GET  /api/ratings/:userId/history      — Rating progression over time
GET  /api/ratings/leaderboard          — Top players (filter: league, org)
POST /api/ratings/recalculate/:tid     — Recalculate from a finalized rated OTB tournament (admin)
GET  /api/ratings/provisional          — Provisional players (separate listing)
```

**Removed from earlier draft:** `POST /api/ratings/fide/link/:userId` and the `fide` key in `GET /api/ratings/:userId` response. No FIDE endpoints exist.

### 3.6 Backend Implementation

**`backend/services/elo_calculator.py`** — pure math, no DB access:
- `expected_score(player_rating, opponent_rating)` — Elo expected score
- `update_rating(player_rating, opponent_rating, result, k_factor)` — single-game update
- `update_ratings_batch(games)` — tournament batch (processes all games, returns rating change list)
- `get_k_factor(games_played, current_rating)` — 40/20/10 selection
- `assign_league(rating)` — C/B/A/Master from rating threshold
- `is_provisional(games_played)` — < 30 games

**`backend/services/rating_service.py`** — DB-backed orchestration:
- `recalculate_ratings_for_tournament(tournament_id)` — gates on tournament being finalized AND `is_rated = true` AND `tournament_mode = 'offline'`. Reads `tournament_games`, applies Elo, writes to `player_ratings` and `rating_history`.

**Removed from earlier draft:** `backend/services/fide_sync.py` is deleted in its entirety. No FIDE service exists in the codebase.

### 3.7 Frontend Components

- **`RatingBadge`** — inline badge: rating number + league icon + "Provisional" tag if < 30 games
- **`RatingChart`** — line chart (rating over time)
- **`LeagueBadge`** — C/B/A/Master with colored icon
- **`Leaderboard`** — `/leaderboard` page: org-scoped + global toggle, provisional separated

**Removed from earlier draft:** `FideCard` component. No FIDE display exists in the UI.

### 3.8 Acceptance Criteria (Rating)

- [ ] New player starts at 1200 rating, K=40, is_provisional=true
- [ ] After a finalized rated OTB tournament: rating updates correctly per Elo formula
- [ ] Online tournaments (`tournament_mode='online'`) do **not** affect rating, even when finalized
- [ ] Unrated tournaments (`is_rated=false`) do **not** affect rating, even when offline
- [ ] K-factor is 40 for first 30 games, 20 for rating < 2300, 10 for ≥ 2300
- [ ] League assigns correctly based on rating thresholds
- [ ] Provisional players (< 30 games) show "Unrated" badge
- [ ] Provisional players don't appear on main leaderboard
- [ ] Rating chart shows progression over time
- [ ] Leaderboard supports org-scoped and global views
- [ ] Rating floor of 800 is enforced
- [ ] No FIDE endpoint, table, service, or component exists anywhere in the codebase

---

## 4. Feature 3: Tournament Calendar

### 4.1 Database Schema

```sql
CREATE TABLE tournaments (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  location TEXT NOT NULL,                     -- venue + address
  location_coordinates POINT,                 -- lat/lng for map
  city TEXT,
  country TEXT DEFAULT 'KZ',
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  registration_deadline TIMESTAMPTZ NOT NULL,
  time_control TEXT NOT NULL,                 -- "90+30", "15+10", etc.
  format TEXT                                 -- Swiss, Round Robin, Knockout
    CHECK (format IN ('swiss', 'round_robin', 'knockout', 'other')),
  max_participants INT,
  entry_fee DECIMAL(10,2) DEFAULT 0,
  currency TEXT DEFAULT 'KZT',
  prize_fund DECIMAL(10,2),
  prize_distribution JSONB,                   -- {"1": 50000, "2": 30000, ...}
  age_categories TEXT[],                      -- {'U8', 'U10', 'U12', 'Open'}
  rating_category TEXT,                       -- league: C, B, A, Open
  min_rating INT,
  max_rating INT,
  -- Rating system gates (replaces is_fide_rated):
  is_rated BOOLEAN DEFAULT false,             -- if true AND tournament_mode='offline', results update Local App Rating
  tournament_mode TEXT NOT NULL DEFAULT 'offline'
    CHECK (tournament_mode IN ('offline', 'online')),  -- only offline tournaments can be rated
  organizer_org_id UUID REFERENCES organizations(id),
  created_by TEXT NOT NULL,                   -- Clerk user ID
  status TEXT DEFAULT 'upcoming'
    CHECK (status IN ('upcoming', 'registration_open', 'registration_closed',
                      'in_progress', 'completed', 'cancelled')),
  rules_url TEXT,
  image_url TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tournaments_status ON tournaments(status);
CREATE INDEX idx_tournaments_dates ON tournaments(start_date, end_date);
CREATE INDEX idx_tournaments_org ON tournaments(organizer_org_id);

CREATE TABLE tournament_registrations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  player_name TEXT NOT NULL,
  rating_at_registration INT,                 -- snapshot at registration time
  age_category TEXT,
  payment_status TEXT DEFAULT 'pending'
    CHECK (payment_status IN ('pending', 'paid', 'refunded', 'waived')),
  whop_checkout_id TEXT,                      -- Whop checkout session ID (if entry fee paid)
  registration_status TEXT DEFAULT 'pending'
    CHECK (registration_status IN ('pending', 'confirmed', 'waitlisted', 'cancelled')),
  registered_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tournament_id, user_id)
);

CREATE TABLE tournament_games (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  round INT NOT NULL,
  board INT,                                  -- board number
  white_player_id TEXT NOT NULL,
  black_player_id TEXT NOT NULL,
  result TEXT NOT NULL                        -- '1-0', '0-1', '1/2-1/2', '*', '+/-', '-/+'
    CHECK (result IN ('1-0', '0-1', '1/2-1/2', '*', '+/-', '-/+')),
  white_rating_before FLOAT,                  -- for performance calc
  black_rating_before FLOAT,
  pgn TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  UNIQUE(tournament_id, round, board)
);

CREATE TABLE tournament_standings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tournament_id UUID NOT NULL REFERENCES tournaments(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  rank INT,
  score FLOAT DEFAULT 0,                      -- points (1/0.5/0)
  buchholz FLOAT DEFAULT 0,                   -- primary tiebreak
  sonneborn_berger FLOAT DEFAULT 0,           -- secondary tiebreak
  wins INT DEFAULT 0,
  draws INT DEFAULT 0,
  losses INT DEFAULT 0,
  rating_change FLOAT,
  performance_rating FLOAT,
  UNIQUE(tournament_id, user_id)
);
```

### 4.2 API Endpoints

**New Flask blueprint: `backend/routes/tournaments.py`**

```
# Public
GET    /api/tournaments                     — List with filters
GET    /api/tournaments/:id                 — Detail
GET    /api/tournaments/:id/participants    — Registered players
GET    /api/tournaments/:id/results         — Standings + results
GET    /api/tournaments/:id/games           — Game results by round
GET    /api/tournaments/calendar            — Calendar view (month/week)

# Authenticated
POST   /api/tournaments/:id/register        — Register (+ Whop payment if fee > 0)
DELETE /api/tournaments/:id/register        — Cancel registration

# Admin only (org admin or super admin)
POST   /api/tournaments                     — Create tournament
PUT    /api/tournaments/:id                 — Update tournament
DELETE /api/tournaments/:id                 — Cancel tournament
POST   /api/tournaments/:id/results         — Upload results (CSV or JSON)
POST   /api/tournaments/:id/pairings        — Enter pairings for a round
POST   /api/tournaments/:id/finalize        — Finalize results + trigger rating calc
```

**Listing filters:**
- `city`, `country` — location
- `date_from`, `date_to` — date range
- `rating_category` — league level
- `age_category` — U8, U10, etc.
- `status` — upcoming, in_progress, completed
- `org_id` — tournaments by specific school

### 4.3 Payment Integration (Whop)

1. User clicks "Register" on tournament page
2. If `entry_fee > 0`:
   - Frontend calls `POST /api/tournaments/:id/register`
   - Backend creates a Whop one-time checkout link (tournament-specific plan), returns `checkoutUrl`
   - Frontend redirects to Whop Checkout (same pattern as existing individual subscription flow)
   - On success: Whop webhook fires → updates `payment_status = 'paid'`, `registration_status = 'confirmed'`
3. If `entry_fee = 0`: auto-confirm, skip payment

**Refund policy:**
- Before registration deadline → admin cancels membership via Whop API → refund
- After deadline → manual admin refund only via Whop dashboard

### 4.4 Frontend Pages

**New routes:**
- `/tournaments` — Calendar/list view with filters
- `/tournaments/:id` — Detail + register button
- `/tournaments/:id/results` — Standings + round-by-round
- `/tournaments/:id/register` — Registration form + Whop payment redirect

**Components:**
- `TournamentCalendar` — month/week/list toggle (month default)
- `TournamentCard` — preview: name, date, location, fee, spots remaining
- `TournamentDetail` — full info, countdown to deadline, eligibility check
- `TournamentFilters` — dropdowns: location, date range, rating, age
- `TournamentResults` — standings table + cross-table + round navigator
- `RegistrationForm` — player info + age category + Whop checkout redirect

### 4.5 Admin Tournament Management

Added to the admin panel (§2.5):

- `/admin/tournaments` — list all org's tournaments
- `/admin/tournaments/new` — create tournament form
- `/admin/tournaments/:id/edit` — edit tournament details
- `/admin/tournaments/:id/pairings` — round-by-round pairing entry
- `/admin/tournaments/:id/results` — upload/edit results, finalize

**Results upload options:**
- CSV upload (columns: round, board, white_name, black_name, result)
- Manual entry form (row per game)
- "Finalize" button: locks results + triggers Elo recalculation

### 4.6 Pairing Strategy

**v1 (this PRD): Manual pairing only.**
- Arbiter enters pairings round-by-round in Chesster admin
- System records and displays, does not generate pairings
- Arbiters keep using their own tools (Swiss Manager, etc.)
- Zero pairing bug risk

**v2 (future): Simplified Swiss for online events.**
- Score grouping → rating-sorted → top-half vs bottom-half
- Color balancing + avoid repeat pairings
- For club events without dedicated arbiter

**v3 (future): Full FIDE-compliant pairing via `bbpPairings`.**

### 4.7 Acceptance Criteria (Tournaments)

- [ ] Admin can create tournament with all fields
- [ ] Tournament appears in calendar view on correct dates
- [ ] Users can filter by city, date, rating, age category
- [ ] Registration enforces deadline, max participants, rating eligibility
- [ ] Entry fee payment via Whop works (including KZT currency)
- [ ] Free tournaments auto-confirm without payment
- [ ] Refund before deadline is automatic
- [ ] Admin can enter pairings round-by-round
- [ ] Admin can upload results via CSV
- [ ] "Finalize" triggers Elo rating recalculation for all participants **only when `is_rated=true` AND `tournament_mode='offline'`** (otherwise no rating change)
- [ ] Standings page shows Buchholz + Sonneborn-Berger tiebreaks
- [ ] Past tournament results are browsable

---

## 5. Implementation Phases

### Phase 1: Foundation — Multi-Tenancy + RBAC
**Scope:** Database schema, RLS, Clerk Organizations sync, subdomain middleware

**Tasks:**
1. Supabase migration: create `organizations`, `organization_members`, `organization_content`, `organization_billing`
2. Supabase migration: add `organization_id` to `user_progress`, `lesson_chat_history`, `coaching_sessions`, `user_games`, `user_chess_profiles`
3. Write RLS policies for all tenant-scoped tables
4. Create `frontend/middleware.ts` with subdomain extraction + org resolution
5. Create `frontend/src/contexts/OrganizationContext.tsx`
6. Clerk Organizations webhook handler: sync org create/update/delete/member events to Supabase
7. Vercel: add `*.chesster.io` as project domain (auto wildcard Let's Encrypt) + wildcard DNS `CNAME * → cname.vercel-dns.com` at registrar — see §7 Infrastructure

**Backend changes:**
- `backend/app.py`: register new blueprints
- `backend/services/supabase_client.py`: add org-scoped query helpers

**Acceptance:** A request to `test.chesster.io` resolves to the correct org. RLS prevents cross-org data access. Clerk org members sync to Supabase.

### Phase 2: White Label Branding + Admin Shell
**Scope:** Visual theming, admin panel skeleton, student management

**Tasks:**
1. CSS custom properties system: `--brand-primary`, `--brand-secondary`, `--brand-accent` injected from org config
2. Dynamic logo + favicon injection in `layout.tsx`
3. Landing page renderer from `landing_page_config` JSONB
4. Admin panel layout + route guard (check role in `organization_members`)
5. `/admin/dashboard` — student count, engagement overview
6. `/admin/students` — list, invite via email, remove, view progress
7. `/admin/courses` — toggle visibility, drag-to-reorder
8. `/admin/settings` — logo upload (Supabase Storage), color picker, preview

**Acceptance:** School admin configures branding → subdomain shows their brand. Admin can manage students and curate courses.

### Phase 3: Billing (Whop)
**Scope:** Org subscription, per-seat billing, tier auto-adjustment

**Tasks:**
1. Create Whop plans for org tiers (Starter, Growth, Enterprise) in Whop dashboard
2. Extend existing `/api/whop/webhook` to handle org membership events (store `organization_id` from metadata)
3. `/api/whop/org-checkout` endpoint: generates Whop checkout URL with org metadata
4. Metered billing logic: count students → track tier in DB (Whop charges flat plan, we track per-seat internally)
5. `/admin/billing` page: current plan, student count, Whop membership status
6. Auto-tier: when student count crosses threshold, upgrade Whop plan via Whop API

**Acceptance:** Org subscribes via Whop. Admin sees plan, student count, billing status. Tier upgrades when thresholds crossed.

### Phase 4: Tournament Calendar
**Scope:** Tournament CRUD, calendar UI, registration, payment

**Tasks:**
1. Supabase migration: `tournaments`, `tournament_registrations`, `tournament_games`, `tournament_standings`
2. Flask blueprint: `backend/routes/tournaments.py` with all endpoints
3. `/tournaments` page: calendar view with month/week/list toggle + filters
4. `/tournaments/:id` page: detail + countdown + register button
5. Registration flow: eligibility check → form → Whop checkout redirect (if fee > 0)
6. `/admin/tournaments/new` + `/admin/tournaments/:id/edit`
7. Tournament listing filters: city, date, rating, age category

**Acceptance:** Tournaments show on calendar. Users can register + pay. Admins can create/edit tournaments.

### Phase 5: Rating System (Local App Rating, Elo, OTB-only)
**Scope:** Internal Elo rating engine, leagues, leaderboard. No FIDE integration.

**Tasks:**
1. Supabase migration: `player_ratings`, `rating_history` only. **No `player_fide_ratings` table.**
2. `backend/services/elo_calculator.py` — pure Elo math (expected score, K-factor, update, league assign)
3. `backend/services/rating_service.py` — DB-backed orchestration; gates on `is_rated AND tournament_mode='offline'`
4. `backend/routes/ratings.py` — rating API endpoints; **no `/fide/link/`, no `fide` response key**
5. `RatingBadge`, `RatingChart`, `LeagueBadge` components. **No `FideCard`.**
6. `/leaderboard` page: org + global views, provisional separated
7. Rating display on profile page
8. Tournament eligibility gating by rating/league

**Acceptance:** Elo correctly calculates ratings after a finalized rated OTB tournament. K-factors apply correctly (40/20/10). Leagues assign by rating threshold. Leaderboard shows org-scoped and global. Online or unrated tournaments leave ratings untouched on finalize. No FIDE endpoint, table, service, or component exists anywhere in the codebase.

### Phase 6: Tournament Results + Rating Integration
**Scope:** Results entry, standings, auto-rating-update

**Tasks:**
1. Manual pairing entry UI in admin
2. Results upload: CSV + manual entry form
3. Standings page: score, Buchholz, Sonneborn-Berger, rating change
4. "Finalize" button: locks results → triggers Elo recalculation via `elo_calculator.update_ratings_batch()`
5. Rating history entries created for each tournament game
6. Historical results archive (past tournaments browsable)
7. Anti-gaming: flag suspicious patterns, min 5 games for leaderboard

**Acceptance:** Admin enters pairings + results. Finalize triggers correct rating updates. Standings show all tiebreaks. Past tournaments are browsable.

---

## 6. Technical Decisions

### Payment: Stay on Whop
**Decision: Keep Whop for everything.**
- Already integrated and working for individual subscriptions (weekly/monthly/yearly)
- Whop supports one-time payments (tournament entry fees) via checkout links
- Single payment provider = no migration needed, simpler reconciliation
- Create separate Whop plans for org tiers (flat rate per tier, we track per-seat internally)
- Per-seat metering handled in our DB — Whop charges the tier plan price
- Tournament fees = one-time Whop products created per tournament

### Clerk Organizations
**Decision: Use Clerk Organizations.**
- Built-in org support (invites, roles, members)
- Already using Clerk — zero auth migration
- SSO per org possible in future
- Webhook sync to Supabase `organizations` table

### PowerSync Scoping
- Add `organization_id` to sync rules
- Students only sync data within their org
- Cross-org isolation at sync layer

### Rating System
**Decision: Single internal "Local App Rating" using the Elo formula. OTB-only.**
- Single rating per (user, org). No time-control pools.
- K-factor system: 40 (provisional, <30 games) / 20 (normal) / 10 (2300+).
- Starting rating 1200 (lower than typical defaults for younger audience).
- **Updated only by finalized rated OTB tournaments.** Online events and non-rated tournaments do not affect the rating.
- **No FIDE integration at all** — no FIDE IDs stored, no official FIDE ratings fetched/displayed, no FIDE API calls. Like Chess.com and Lichess, we run our own internal pool.
- Simple, proven, no exotic algorithms.

### Tournament Pairing
**Decision: Manual first, automated later.**
- v1: arbiter enters pairings manually
- v2: simplified Swiss for online events
- v3: full FIDE-compliant via bbpPairings (if demand)

### Database Migrations
- Supabase migrations in `supabase/migrations/`
- Backward-compatible: add columns nullable first, backfill, enforce
- Zero-downtime: no breaking changes in single migration

---

## 7. Infrastructure Changes

### Domain / SSL (Vercel)
*Updated 2026-06-01: original PRD assumed VPS + Nginx + certbot. Chesster is now Vercel-primary (see ADR-0004), so the mechanism below replaces the certbot path. The acceptance criterion — wildcard SSL works for any `*.chesster.io` subdomain — is unchanged.*

- Add `*.chesster.io` as a domain on the Chesster Vercel project (dashboard → Settings → Domains, or `vercel domains add '*.chesster.io'`)
- Vercel issues a wildcard Let's Encrypt cert automatically (one level only — nested wildcards not covered)
- At the registrar hosting `chesster.io`, add a wildcard CNAME: `* → cname.vercel-dns.com` (or A-record to Vercel's anycast IP — Vercel will show the exact record). Set DNS-only / non-proxied if Cloudflare ever fronts the domain
- VPS Nginx is **not** in the request path for `*.chesster.io`; tenant subdomains go straight to Vercel's edge
- Future: per-tenant custom domain (`chess.schoolname.com`) added via Vercel Domains API as a paid upgrade

### New Environment Variables
```
WHOP_API_KEY=...                          -- Whop API key (for creating checkouts, managing memberships)
WHOP_WEBHOOK_SECRET=...                   -- Whop webhook verification (if not already set)
NEXT_PUBLIC_WHOP_ORG_STARTER_PLAN=plan_...  -- Org tier: Starter
NEXT_PUBLIC_WHOP_ORG_GROWTH_PLAN=plan_...   -- Org tier: Growth
NEXT_PUBLIC_WHOP_ORG_ENTERPRISE_PLAN=plan_... -- Org tier: Enterprise
```
(Individual plan env vars already exist: `NEXT_PUBLIC_WHOP_WEEKLY_PLAN`, `MONTHLY`, `YEARLY`)

### Monitoring
- PostHog: add `org_id` as group property for org-level analytics
- PM2: no changes (single process handles all subdomains)

---

## 8. File Impact Summary

### New Files

**Frontend:**
- `frontend/middleware.ts` — subdomain routing
- `frontend/src/contexts/OrganizationContext.tsx` — tenant context provider
- `frontend/src/app/admin/layout.tsx` — admin shell + role guard
- `frontend/src/app/admin/dashboard/page.tsx`
- `frontend/src/app/admin/students/page.tsx`
- `frontend/src/app/admin/courses/page.tsx`
- `frontend/src/app/admin/billing/page.tsx`
- `frontend/src/app/admin/settings/page.tsx`
- `frontend/src/app/admin/analytics/page.tsx`
- `frontend/src/app/admin/tournaments/page.tsx`
- `frontend/src/app/admin/tournaments/new/page.tsx`
- `frontend/src/app/admin/tournaments/[id]/edit/page.tsx`
- `frontend/src/app/admin/tournaments/[id]/pairings/page.tsx`
- `frontend/src/app/admin/tournaments/[id]/results/page.tsx`
- `frontend/src/app/tournaments/page.tsx`
- `frontend/src/app/tournaments/[id]/page.tsx`
- `frontend/src/app/tournaments/[id]/results/page.tsx`
- `frontend/src/app/tournaments/[id]/register/page.tsx`
- `frontend/src/app/leaderboard/page.tsx`
- `frontend/src/components/admin/` — 10+ admin components
- `frontend/src/components/tournaments/` — 6-8 tournament components
- `frontend/src/components/ratings/RatingBadge.tsx`
- `frontend/src/components/ratings/RatingChart.tsx`
- `frontend/src/components/ratings/LeagueBadge.tsx`
- `frontend/src/components/ratings/Leaderboard.tsx`

**Backend:**
- `backend/routes/__init__.py`
- `backend/routes/tournaments.py` — tournament API blueprint
- `backend/routes/ratings.py` — rating API blueprint
- `backend/routes/admin.py` — admin API blueprint
- `backend/routes/webhooks.py` — Clerk webhook handlers (Whop webhooks stay in Next.js API routes)
- `backend/services/elo_calculator.py` — Pure Elo math for the Local App Rating
- `backend/services/rating_service.py` — DB-backed orchestration; gates rating updates on rated OTB tournaments
- `backend/services/billing_service.py` — Whop API integration (org tier management, tournament fee checkouts)
- `backend/services/tournament_service.py` — tournament business logic

**Database:**
- `supabase/migrations/YYYYMMDD_001_organizations.sql`
- `supabase/migrations/YYYYMMDD_002_add_org_id_to_existing.sql`
- `supabase/migrations/YYYYMMDD_003_tournaments.sql`
- `supabase/migrations/YYYYMMDD_004_ratings.sql`
- `supabase/migrations/YYYYMMDD_005_rls_policies.sql`
- `supabase/migrations/YYYYMMDD_006_tournament_standings.sql`

### Modified Files

- `frontend/src/app/layout.tsx` — wrap with `OrganizationProvider`
- `frontend/src/components/Navbar.tsx` — org-aware logo/name
- `frontend/next.config.ts` — domain config if needed
- `backend/app.py` — register new blueprints
- `backend/services/supabase_client.py` — org-scoped query helpers
- Vercel project domains — add `*.chesster.io` (wildcard cert auto-issued); registrar DNS — add wildcard CNAME to `cname.vercel-dns.com`
- `i18n/` — new translation keys for admin, tournaments, ratings

---

## 9. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cross-tenant data leak | Critical | RLS on every table + org_id in every query + integration tests |
| Whop payment failures | High | Webhook retry handling + manual admin override for payment status |
| Elo calculation error | Medium | Unit tests against hand-computed Elo test vectors + simple formula is easy to verify |
| Rating updated by non-OTB tournament | High | `rating_service.recalculate_ratings_for_tournament` hard-gates on `is_rated AND tournament_mode='offline'` + dedicated unit + integration tests |
| Subdomain SSL issues | Medium | Test wildcard cert renewal automation before launch |
| PowerSync org scoping gaps | Medium | Test offline sync per org before enabling white-label |
| Clerk webhook delivery gaps | Medium | Idempotent handlers + manual sync button in admin |

---

## 10. Success Metrics

| Metric | Target | Timeframe |
|--------|--------|-----------|
| Partner schools onboarded | 5 | 3 months post-launch |
| Students across orgs | 200+ | 3 months post-launch |
| Tournaments created | 10 | 3 months post-launch |
| Tournament registrations (paid) | 50 | 3 months post-launch |
| MRR from org billing | $500+ | 6 months post-launch |
| Rating adoption | 80% of active students rated | 2 months post-launch |

---

## 11. Open Questions

1. **Base price per student?** Need market research for Kazakhstan chess school pricing
2. **Free tier for orgs?** Should there be a free plan (e.g., up to 10 students)?
3. **Custom domains (chess.school.edu)?** Include in v1 or defer to v2?
4. **Tournament fee splitting?** Should orgs receive entry fees directly? (Whop doesn't have Connect-like splitting — manual payouts or Whop affiliate links)

---

## 12. Phase 7 — Platform Super-Admin Dashboard

**Status:** Net new scope, not in original PRD. Original PRD scope was strictly school-facing (`/admin/*` per Clerk Org). Phase 7 introduces a platform-level admin surface (`/super-admin/*`) for Chesster operators to manage all users and all schools.

**Hard-committed sub-phases:** 7A (Foundations) + 7B (Users Dashboard).
**Parked (unlock when needed):** 7C (Schools Dashboard), 7D (Audit Log + Feature Flags).

### 12.1 Locked Decisions

| Decision | Choice |
|----------|--------|
| Role structure | Single `super_admin` role (no tiering) |
| Impersonation depth | Read-only ("view as user"); all writes blocked at API layer |
| Document structure | Append as Phase 7 to this PRD |
| Phase commit | 7A + 7B hard-committed; 7C/7D parked |
| Access control | Clerk role check + mandatory 2FA (no IP allowlist) |

### 12.2 Coverage Audit — Original PRD vs. Requested Scope

| Capability | Original PRD | Status in Code | Phase 7 Adds |
|-----------|-------------|----------------|--------------|
| Manage offline partner schools (create/delete) | Implicit (Clerk Dashboard) | Manual via Clerk Dashboard | UI in 7C |
| Monitor schools (MRR, churn, seat usage) | ❌ Not considered | ❌ | 7C |
| Grant powers / change school plan | ❌ Not considered | ❌ | 7C |
| Manage online users (search/suspend/refund/delete) | ❌ Not considered | ❌ | 7B |
| Impersonate user for support | ❌ Not considered | ❌ | 7B (read-only) |
| Audit log of admin actions | ❌ Not considered | ❌ | 7D |
| Feature flags (gradual rollouts) | ❌ Not considered | ❌ | 7D |
| Two distinct dashboards (users + schools) | ❌ Not considered | ❌ | 7B + 7C |
| Super-admin role separation from school admin | ❌ Not considered | Only school-level `org:admin` exists | 7A |
| Platform-level analytics | ❌ Not considered | ❌ | 7B/7C dashboards |

**Conclusion:** every super-admin capability the user requested is net new. The original PRD only addresses school admins acting within their own org.

### 12.3 Architecture Overview

**Routing:**
- `/super-admin/*` rendered ONLY on apex `chesster.io`. Subdomains (school.chesster.io) reject the route at middleware level.
- `frontend/middleware.ts` extends to (a) detect apex host, (b) check Clerk `publicMetadata.platform_role === "super_admin"`, (c) check 2FA enabled, redirect to `/sign-in?reason=2fa-required` otherwise.

**Auth:**
- Role stored in Clerk `publicMetadata.platform_role` (string: `"super_admin" | null`).
- Backend middleware `require_super_admin()` decorator validates Clerk JWT + role on every `/api/super-admin/*` request.
- 2FA enforced via Clerk's session_token claim `two_factor`.

**Data sources:**
- **Users:** Clerk (source of truth for identity) + Supabase (subscription/profile data) + Whop (billing). Aggregated into `platform_user_cache` for fast search.
- **Schools:** Existing `organizations` + `organization_members` tables, joined with Whop org subscriptions.

**Two top-level dashboards:**
1. `/super-admin/users` — online individual users (no org affiliation OR cross-org view)
2. `/super-admin/schools` — partner offline schools (Phase 7C, parked)

Plus shells: `/super-admin/audit`, `/super-admin/flags`, `/super-admin/settings` (7D, parked).

### 12.4 Database Schema (New Tables)

```sql
-- 7A: role + audit foundations
CREATE TABLE platform_admin_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_clerk_id TEXT NOT NULL,
  action TEXT NOT NULL,                -- 'user.suspend', 'user.refund', 'school.plan_change', 'impersonate.start', etc.
  target_type TEXT NOT NULL,           -- 'user' | 'organization' | 'system'
  target_id TEXT NOT NULL,
  payload JSONB,                       -- before/after diff, reason, etc.
  ip_address INET,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_audit_admin ON platform_admin_audit_log(admin_clerk_id, created_at DESC);
CREATE INDEX idx_audit_target ON platform_admin_audit_log(target_type, target_id, created_at DESC);

-- 7A: read-only impersonation tracking
CREATE TABLE impersonation_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_clerk_id TEXT NOT NULL,
  target_clerk_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  ip_address INET
);

-- 7B: cached user state for fast platform-level search
CREATE TABLE platform_user_status (
  clerk_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'active',  -- 'active' | 'suspended' | 'banned' | 'deleted'
  suspended_reason TEXT,
  suspended_at TIMESTAMPTZ,
  suspended_by TEXT,                       -- admin clerk_id
  notes TEXT,                              -- internal admin notes
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7B: search index, denormalised from Clerk + Whop + Supabase
CREATE TABLE platform_user_cache (
  clerk_id TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  name TEXT,
  signup_at TIMESTAMPTZ,
  last_seen_at TIMESTAMPTZ,
  subscription_status TEXT,                -- 'free' | 'weekly' | 'monthly' | 'yearly' | 'cancelled'
  whop_membership_id TEXT,
  org_count INT DEFAULT 0,                 -- how many orgs they belong to
  total_revenue_cents INT DEFAULT 0,
  refreshed_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_user_cache_email ON platform_user_cache USING gin (email gin_trgm_ops);
CREATE INDEX idx_user_cache_name ON platform_user_cache USING gin (name gin_trgm_ops);

-- 7D (parked): feature flags
CREATE TABLE feature_flags (
  key TEXT PRIMARY KEY,
  enabled BOOLEAN DEFAULT FALSE,
  rollout_percent INT DEFAULT 0,           -- 0-100, for gradual rollouts
  allowlist_clerk_ids TEXT[] DEFAULT '{}',
  allowlist_org_ids UUID[] DEFAULT '{}',
  description TEXT,
  updated_by TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 12.5 Backend Design (Phase 7A + 7B)

**New blueprint:** `backend/routes/super_admin.py`

**Auth decorator:** `backend/utils/auth.py::require_super_admin()`
- Validates Clerk JWT
- Checks `publicMetadata.platform_role === "super_admin"`
- Checks `two_factor` claim
- Logs every successful call to `platform_admin_audit_log`

**Endpoints (7A):**
- `GET  /api/super-admin/me` — verify role, return admin profile
- `GET  /api/super-admin/audit?limit=100&cursor=...` — read audit log (read-only in 7A)

**Endpoints (7B):**
- `GET  /api/super-admin/users?q=&status=&plan=&cursor=&limit=` — paginated user search via `platform_user_cache`
- `GET  /api/super-admin/users/:clerkId` — full user detail (Clerk + Supabase + Whop)
- `PATCH /api/super-admin/users/:clerkId/status` — suspend/unsuspend/ban; body: `{status, reason}`
- `POST /api/super-admin/users/:clerkId/refund` — issue Whop refund; body: `{amount_cents, reason}`
- `DELETE /api/super-admin/users/:clerkId` — soft-delete (sets status=deleted, anonymises PII per GDPR)
- `POST /api/super-admin/users/:clerkId/impersonate` — start read-only impersonation; returns short-lived token
- `DELETE /api/super-admin/users/:clerkId/impersonate` — end impersonation session

**Read-only impersonation enforcement:**
- Impersonation session issues a Clerk session token with custom claim `impersonated_by: <admin_clerk_id>`.
- ALL backend write endpoints check: `if claims.get('impersonated_by'): return 403`.
- All reads proceed normally (admin sees what user sees).
- Session auto-expires after 30 min; logged start + end in `impersonation_sessions`.

**Cache warming:**
- New service `backend/services/platform_user_cache_service.py`.
- Webhooks `user.created`, `user.updated`, `user.deleted` (Clerk) and `membership.*` (Whop) upsert into `platform_user_cache`.
- Nightly cron `scripts/refresh_platform_user_cache.py` to reconcile drift.

### 12.6 Frontend Design (Phase 7A + 7B)

**Route structure:**
```
frontend/src/app/super-admin/
├── layout.tsx              # 7A: auth guard, sidebar shell, impersonation banner
├── page.tsx                # 7A: dashboard home (system stats: total users, MRR, schools)
├── users/
│   ├── page.tsx            # 7B: user list (search + filter)
│   ├── [clerkId]/
│   │   ├── page.tsx        # 7B: user detail (overview, subscription, sessions, audit history)
│   │   └── actions.tsx     # 7B: suspend/refund/delete/impersonate buttons
│   └── components/
│       ├── UserSearchBar.tsx
│       ├── UserFilters.tsx
│       ├── UserTable.tsx
│       ├── UserStatusBadge.tsx
│       └── ImpersonateButton.tsx
├── audit/                  # 7A read-only viewer; 7D adds export
│   └── page.tsx
└── components/
    ├── SuperAdminSidebar.tsx
    ├── ImpersonationBanner.tsx  # red banner top of every page when impersonating
    └── PlatformStats.tsx
```

**Middleware extension** (`frontend/middleware.ts`):
- Apex host check (no `chesster.io` subdomain prefix).
- Block route if host has subdomain → 404.
- Block if user lacks `platform_role === 'super_admin'` → 403.
- Block if 2FA not enabled → redirect `/account/security?reason=2fa-required`.

**Impersonation UX:**
- Click "View as" on user detail → backend issues impersonation token → frontend stores in separate cookie (`__impersonation`).
- Loud red banner across entire app: "Impersonating <email> (read-only) — [Exit]".
- All write buttons disabled client-side as belt-and-braces; server enforces.
- Banner stays until admin clicks Exit or token expires.

**Stack alignment with existing app:**
- Next.js 16 App Router + Server Components for data fetching.
- ShadCN UI components for tables, dialogs, forms.
- TanStack Query for client-side mutations + optimistic updates.
- Zod schemas shared with backend for request validation.

### 12.7 Backend ↔ Frontend Contract

**Request flow (suspend user example):**
1. Admin clicks "Suspend" → confirmation dialog asks for reason.
2. Frontend `PATCH /api/super-admin/users/:clerkId/status` with `{status: 'suspended', reason: '...'}`.
3. Backend `require_super_admin` decorator validates JWT + 2FA + role.
4. Backend updates `platform_user_status`, calls Clerk API to revoke sessions, writes audit log.
5. Backend returns updated user object; frontend refreshes detail panel + invalidates list cache.

**Type sharing:** generate TS types from Pydantic models via `datamodel-codegen` into `frontend/src/types/super-admin.ts`.

### 12.8 Phase 7A — Foundations (Hard-committed)

**Deliverables:**
- Migration: `00X_platform_admin_foundations.sql` (audit log, impersonation_sessions, status, user_cache, role columns).
- Backend: `super_admin.py` blueprint with `/me` + `/audit` + auth decorator.
- Frontend: `/super-admin` shell, layout, sidebar, auth guard middleware.
- Set Alex's Clerk publicMetadata `platform_role = "super_admin"` manually.
- 2FA enforcement check in middleware.
- Audit log viewer (read-only).

**Acceptance:**
- Visiting `/super-admin` as Alex with 2FA on → loads dashboard.
- Visiting as anyone else → 403.
- Visiting on a school subdomain → 404.
- Every API call appears in `platform_admin_audit_log`.

### 12.9 Phase 7B — Users Dashboard (Hard-committed)

**Deliverables:**
- `platform_user_cache_service.py` + webhook handlers + nightly cron.
- All `/api/super-admin/users/*` endpoints.
- User list page with search (email/name fuzzy via pg_trgm), filters (status, plan, signup date).
- User detail page: profile, subscription, recent activity, audit history per user.
- Action buttons: suspend, unsuspend, refund (Whop API), soft-delete, impersonate (read-only).
- Read-only impersonation flow + banner.
- Confirmation dialogs for all destructive actions; reason required.
- Audit log entry per action.

**Acceptance:**
- Search returns paginated results in <500ms.
- Suspend → user can't sign in; appears in audit log.
- Refund → Whop reflects refund; audit log shows amount + reason.
- Impersonate → admin sees user's `/dashboard`; clicking any write action returns 403 from backend with toast.
- Soft-delete → user marked deleted; PII anonymised; account inaccessible.

### 12.10 Phase 7C — Schools Dashboard (PARKED)

Will mirror 7B at the org level: list/search orgs, view metrics (seats, MRR, churn), change plan, suspend, soft-delete. Adds `POST /api/super-admin/orgs` to create new orgs (replaces Clerk Dashboard manual flow). Unlock when partner-school count makes manual ops painful (~3+ schools).

### 12.11 Phase 7D — Audit + Feature Flags (PARKED)

- Audit log: filters, export to CSV, retention policy (default keep forever).
- Feature flags: CRUD UI, gradual rollout slider, allowlist by clerk_id or org_id, eval cache for backend/frontend.
- Unlock when (a) Alex hires a second admin or (b) needs gradual feature rollouts.

### 12.12 Risks & Mitigations (Phase 7)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Privilege escalation via Clerk metadata tampering | Critical | Backend always re-validates role via Clerk API; never trusts client claim |
| Impersonation abuse | High | Read-only enforcement at API + audit log + 30-min auto-expiry |
| Stolen super-admin session | High | Mandatory 2FA + short Clerk session lifetime (1h) + audit log alerts on anomalies |
| Cache drift (user_cache vs Clerk) | Medium | Webhook-driven updates + nightly reconcile cron + admin manual refresh button |
| GDPR delete incompleteness | Medium | Soft-delete anonymises PII in cache + Clerk + Supabase profiles in single transaction |
| Audit log tampering | Medium | RLS denies UPDATE/DELETE on audit table for everyone except service role |

### 12.13 Success Metrics (Phase 7)

| Metric | Target | Timeframe |
|--------|--------|-----------|
| Time to find any user from email/name | <30s | Post-7B |
| Support actions performed via dashboard (not Clerk Dashboard) | 100% | Post-7B |
| Avg impersonation session duration | <10 min | Post-7B (longer = misuse signal) |
| Audit log queries before any user-facing action | 100% | Always |

### 12.14 Open Questions (Phase 7)

1. **Anomaly alerting?** Should suspicious admin behaviour (e.g., 50+ impersonations in 1h) trigger Telegram alert to Alex? — defer to Phase 7D.
2. **Refund partial vs full?** Whop API supports partial; should the UI default to full or show line items? — default full, allow override.
3. **Bulk actions?** E.g., "suspend all accounts created via this leaked invite link" — defer until concrete need arises.
4. **Audit retention?** Forever vs N years? — default forever, add archival policy in 7D.
5. **Sub-admins beyond Alex?** Single role assumes one admin; if a support hire is added, revisit the tiering decision (currently locked as single).
