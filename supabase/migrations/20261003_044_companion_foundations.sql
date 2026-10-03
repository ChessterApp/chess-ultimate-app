-- ============================================================================
-- 20261003_044_companion_foundations.sql
-- Companion Phase 0 — Foundations (.ralphy/companion-phase0-brief.md)
--
-- The persistence floor for the companion vertical slice (architecture plan
-- A3/A5/A7): companion state, the versioned competency layer, a server-issued
-- assessment pipeline (definitions/assignments/attempts), a concept-scoped
-- SM-2 mastery scheduler, and an append-only domain-event audit trail. Also
-- extends the coin_ledger.source enum with companion earning reasons.
--
-- Subject key: Clerk `owner_user_id` (TEXT = JWT `sub`), per decision A3 — these
-- tables are per-child, NOT (org, student). Earning writes bridge owner →
-- (org, student) at the ledger boundary only; the ledger keeps its CE keying.
--
-- Security model:
--  • Owner-read tables (companion, mastery_state, task_assignment): RLS on,
--    authenticated SELECT only own rows via public.clerk_uid() — matches the
--    opening-repertoire / wheel_presets owner idiom (20260914_039).
--  • competency_definition: public catalog, read-all for authenticated.
--  • Server-only lockdown (competency_evidence, task_definition, task_attempt,
--    domain_event): RLS on, REVOKE from anon/authenticated — the 20260918_042
--    pattern. task_definition holds answer keys (solution), so it is NEVER
--    client-readable; assessment payloads are assembled server-side.
--  All writes are service-role only (Next.js route handlers, BYPASSRLS).
--
-- Idempotent: safe to re-run (IF NOT EXISTS / ON CONFLICT DO NOTHING). Reuses
-- gamification_touch_updated_at() from 20260817_033 and public.clerk_uid() from
-- 20260601_008. Flag-dark: nothing reads these tables until a later phase.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- companion — one row per owner (unique). Pre-hatch state = no row or 'egg'
-- stage; a companion hatches into 'hatched' with a chosen species + name.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companion (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id  TEXT NOT NULL UNIQUE,            -- Clerk user id (A3)
  species        TEXT,                            -- e.g. 'fox'; chosen at egg select
  name           TEXT,                            -- set at hatch
  stage          TEXT NOT NULL DEFAULT 'egg' CHECK (stage IN ('egg','hatched')),
  hatched_at     TIMESTAMPTZ,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_companion_updated ON companion;
CREATE TRIGGER trg_companion_updated
  BEFORE UPDATE ON companion
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ---------------------------------------------------------------------------
-- competency_definition — versioned concept catalog (global, not org-scoped).
-- `code` is the stable identifier referenced by evidence/mastery/tasks. Lesson
-- mapping refs point at existing Chess Basics content (audit §2).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competency_definition (
  code           TEXT PRIMARY KEY,                -- e.g. 'H_ROOK'
  title_en       TEXT NOT NULL,
  title_ru       TEXT NOT NULL,
  title_kk       TEXT NOT NULL,
  course_slug    TEXT,                            -- lesson mapping ref (NULL = no content yet)
  lesson_title   TEXT,                            -- lesson mapping ref
  sort_order     INT NOT NULL DEFAULT 0,
  active         BOOLEAN NOT NULL DEFAULT true,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_competency_definition_updated ON competency_definition;
CREATE TRIGGER trg_competency_definition_updated
  BEFORE UPDATE ON competency_definition
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ---------------------------------------------------------------------------
-- competency_evidence — append-only demonstration records (A5/§11.2). Written
-- inside the reward transaction; never client-readable (server-only lockdown).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS competency_evidence (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id   TEXT NOT NULL,
  competency_code TEXT NOT NULL REFERENCES competency_definition(code) ON DELETE CASCADE,
  kind            TEXT NOT NULL,                  -- 'assessment' | 'review' | 'placement'
  source_attempt_id UUID,                         -- task_attempt the evidence derives from
  correct         BOOLEAN NOT NULL,
  assistance_used BOOLEAN NOT NULL DEFAULT false,
  policy_version  TEXT NOT NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_competency_evidence_owner
  ON competency_evidence (owner_user_id, competency_code, created_at);

-- ---------------------------------------------------------------------------
-- mastery_state — concept-scoped SM-2 scheduler, ported from the opening
-- trainer (backend/api/openings.py:1764-1918): the same six scheduler columns
-- (ease_factor, interval_days, times_trained, times_correct, last_trained_at,
-- next_review_at) plus next_review_at drives the pull-based due queue (A4).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS mastery_state (
  owner_user_id   TEXT NOT NULL,
  competency_code TEXT NOT NULL REFERENCES competency_definition(code) ON DELETE CASCADE,
  ease_factor     NUMERIC(4,2) NOT NULL DEFAULT 2.5,
  interval_days   INT NOT NULL DEFAULT 0,
  times_trained   INT NOT NULL DEFAULT 0,
  times_correct   INT NOT NULL DEFAULT 0,
  last_trained_at TIMESTAMPTZ,
  next_review_at  TIMESTAMPTZ,
  policy_version  TEXT NOT NULL DEFAULT 'hatch-v1',
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (owner_user_id, competency_code)
);
CREATE INDEX IF NOT EXISTS idx_mastery_state_due
  ON mastery_state (owner_user_id, next_review_at);

DROP TRIGGER IF EXISTS trg_mastery_state_updated ON mastery_state;
CREATE TRIGGER trg_mastery_state_updated
  BEFORE UPDATE ON mastery_state
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ---------------------------------------------------------------------------
-- task_definition — server-side task bank (A7). Holds FEN/prompt AND the answer
-- key (`solution`); SERVER-ONLY so solutions never ship to the client. The
-- assignment route assembles a public payload (FEN + prompt, no solution).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_definition (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  competency_code TEXT NOT NULL REFERENCES competency_definition(code) ON DELETE CASCADE,
  family          TEXT NOT NULL,                  -- task family (groups variants)
  version         INT NOT NULL DEFAULT 1,
  mode            TEXT NOT NULL DEFAULT 'assessment' CHECK (mode IN ('assessment','learning')),
  fen             TEXT NOT NULL,
  prompt_en       TEXT NOT NULL,
  prompt_ru       TEXT NOT NULL,
  prompt_kk       TEXT NOT NULL,
  solution        JSONB NOT NULL,                 -- answer key — NEVER client-readable
  validator       TEXT NOT NULL DEFAULT 'move',   -- chess.js-based validator kind
  hints           JSONB NOT NULL DEFAULT '[]'::jsonb,
  difficulty      TEXT,
  active           BOOLEAN NOT NULL DEFAULT true,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_task_definition_competency
  ON task_definition (competency_code, mode, active);

DROP TRIGGER IF EXISTS trg_task_definition_updated ON task_definition;
CREATE TRIGGER trg_task_definition_updated
  BEFORE UPDATE ON task_definition
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ---------------------------------------------------------------------------
-- task_assignment — a server-issued instance of a task for one owner. Owner may
-- read their own assignments (they need FEN + prompt), but the row carries NO
-- solution; the answer key stays in task_definition (server-only).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_assignment (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id   TEXT NOT NULL,
  task_id         UUID NOT NULL REFERENCES task_definition(id) ON DELETE CASCADE,
  competency_code TEXT NOT NULL REFERENCES competency_definition(code) ON DELETE CASCADE,
  mode            TEXT NOT NULL DEFAULT 'assessment',
  status          TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','attempted','passed','failed')),
  issued_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_task_assignment_owner
  ON task_assignment (owner_user_id, competency_code, status);

-- ---------------------------------------------------------------------------
-- task_attempt — per-attempt record with first-response correctness and
-- assistance flag (the authoritative evidence source). SERVER-ONLY: clients
-- never read raw submissions, and submission_key makes writes idempotent.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS task_attempt (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id   UUID NOT NULL REFERENCES task_assignment(id) ON DELETE CASCADE,
  owner_user_id   TEXT NOT NULL,
  task_id         UUID NOT NULL REFERENCES task_definition(id) ON DELETE CASCADE,
  submission      JSONB,                          -- the move(s) the client submitted
  correct         BOOLEAN NOT NULL,
  first_response  BOOLEAN NOT NULL DEFAULT true,
  assistance_used BOOLEAN NOT NULL DEFAULT false,
  submission_key  TEXT NOT NULL UNIQUE,           -- idempotency guard
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_task_attempt_assignment
  ON task_attempt (assignment_id, created_at);

-- ---------------------------------------------------------------------------
-- domain_event — append-only audit (A5). Written synchronously inside reward
-- transactions; a poller is a later WP. SERVER-ONLY.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS domain_event (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id TEXT NOT NULL,
  event_type    TEXT NOT NULL,                    -- e.g. 'competency.demonstrated'
  payload       JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_domain_event_owner
  ON domain_event (owner_user_id, created_at);

-- ============================================================================
-- coin_ledger.source CHECK extension — add companion earning reasons, keep the
-- existing enum values intact (033 defined: earn_xp, streak, purchase, spend,
-- admin_adjust, refund; single-column constraint auto-named coin_ledger_source_check).
-- ============================================================================
ALTER TABLE coin_ledger DROP CONSTRAINT IF EXISTS coin_ledger_source_check;
ALTER TABLE coin_ledger ADD CONSTRAINT coin_ledger_source_check
  CHECK (source IN (
    'earn_xp','streak','purchase','spend','admin_adjust','refund',
    'earn_learning','competency_pass','due_review','chapter_completion'
  ));

-- ============================================================================
-- Row Level Security
-- ============================================================================

-- Owner-read tables: authenticated SELECT only own rows; writes service-role.
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['companion','mastery_state','task_assignment'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('REVOKE ALL ON %I FROM anon, authenticated;', t);
    EXECUTE format('GRANT SELECT ON %I TO authenticated;', t);
    EXECUTE format('DROP POLICY IF EXISTS "owner_read" ON %I;', t);
    EXECUTE format(
      'CREATE POLICY "owner_read" ON %I FOR SELECT TO authenticated USING (owner_user_id = public.clerk_uid());',
      t
    );
  END LOOP;
END $$;

-- competency_definition: public catalog — read-all for authenticated.
ALTER TABLE competency_definition ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON competency_definition FROM anon, authenticated;
GRANT SELECT ON competency_definition TO authenticated;
DROP POLICY IF EXISTS "read_all" ON competency_definition;
CREATE POLICY "read_all" ON competency_definition
  FOR SELECT TO authenticated USING (true);

-- Server-only lockdown: evidence, task_definition (answer keys), attempts, events.
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['competency_evidence','task_definition','task_attempt','domain_event'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY;', t);
    EXECUTE format('REVOKE ALL ON %I FROM anon, authenticated;', t);
  END LOOP;
END $$;

-- ============================================================================
-- Seed the 9 hatch competencies (spec §4.2), mapped to existing Chess Basics
-- lessons (audit §2). H_SETUP has no content yet (lesson refs NULL). Global
-- catalog, so no org scoping; ON CONFLICT keeps re-runs safe.
-- ============================================================================
INSERT INTO competency_definition (code, title_en, title_ru, title_kk, course_slug, lesson_title, sort_order)
VALUES
  ('H_SETUP',  'Board Setup', 'Расстановка', 'Тақтаны орналастыру', NULL,          NULL,         1),
  ('H_ROOK',   'The Rook',    'Ладья',       'Тура',               'chess-basics', 'The Rook',   2),
  ('H_BISHOP', 'The Bishop',  'Слон',        'Піл',                'chess-basics', 'The Bishop', 3),
  ('H_QUEEN',  'The Queen',   'Ферзь',       'Уәзір',              'chess-basics', 'The Queen',  4),
  ('H_KNIGHT', 'The Knight',  'Конь',        'Ат',                 'chess-basics', 'The Knight', 5),
  ('H_KING',   'The King',    'Король',      'Патша',              'chess-basics', 'The King',   6),
  ('H_PAWN',   'The Pawn',    'Пешка',       'Сарбаз',             'chess-basics', 'The Pawn',   7),
  ('H_CHECK',  'Check',       'Шах',         'Шах',                'chess-basics', 'Check',      8),
  ('H_MATE',   'Checkmate',   'Мат',         'Мат',                'chess-basics', 'Checkmate',  9)
ON CONFLICT (code) DO NOTHING;

COMMIT;

-- ============================================================================
-- ROLLBACK (manual):
--   ALTER TABLE coin_ledger DROP CONSTRAINT IF EXISTS coin_ledger_source_check;
--   ALTER TABLE coin_ledger ADD CONSTRAINT coin_ledger_source_check
--     CHECK (source IN ('earn_xp','streak','purchase','spend','admin_adjust','refund'));
--   DROP TABLE IF EXISTS domain_event, task_attempt, task_assignment, task_definition,
--     mastery_state, competency_evidence, competency_definition, companion CASCADE;
-- ============================================================================
