-- ============================================================================
-- 20261003_048_companion_quests_goal.sql
-- Companion Phase 5 — Pilot polish: weekly practice-days goal + minimal quest
-- strip (.ralph/companion-phase5-task.md).
--
-- Builds on migrations 044 (foundations), 045 (assessment), 046 (hatch),
-- 047 (Watchtower + review). Adds:
--  • weekly_goal defaults in the hatch-v1 reward policy config (spec line 365:
--    DEFAULT three meaningful practice days, user-adjustable, bounds 1..7). The
--    default/bounds live in DATA, never hardcoded in a code path.
--  • companion_weekly_goal — lightweight per-owner goal TARGET override (A3,
--    owner-keyed). Progress is computed at read time from competency_evidence;
--    NO progress/penalty is stored. Missing a week has no penalty and NEVER
--    gates or unlocks anything (R2, hard invariant).
--  • quest_definition — versioned, immutable published quest catalog (spec §7.2):
--    title/copy keys ×3 locales, region, prerequisites, objective list, reward
--    policy ref (reuses an existing companion_reward_policy key — no new reward
--    amounts), replay policy, publish_state. PK (id, version) so published
--    versions are immutable.
--  • quest_progress — per-owner quest state machine (A3): locked → available →
--    active → objectives_complete → completed; UNIQUE(owner, quest, version) so a
--    quest completes at most once per owner (first-completion reward is idempotent
--    on a companion:quest:<owner>:<quest_version> ledger key).
--  • companion_complete_quest() — ONE atomic, idempotent SECURITY DEFINER RPC that
--    verifies objectives server-side from Watchtower evidence (reuses the Phase 4
--    chapter-completion computation — COUNT DISTINCT correct learning families),
--    advances quest_progress to 'completed', and grants the reward exactly once
--    via the existing chapter_completion ledger source + a companion:quest:* key.
--    Repeat play cannot regrant the first-completion reward.
--  • one seeded quest (id 'watchtower', v1) wrapping the shipped Watchtower chapter
--    (objective = complete W01–W06). NO cooperative/expedition quests (deferred).
--
-- No new coin_ledger.source values — the quest reward reuses 'chapter_completion'
-- (already allowed by the 044 CHECK) with its own idempotency key, so it is a
-- distinct grant from the Phase 4 chapter reward. Reuses chapter_first AMOUNTS.
--
-- Idempotent: safe to re-run (IF NOT EXISTS / ON CONFLICT DO NOTHING). Reuses
-- gamification_touch_updated_at() (033) + public.clerk_uid() (008). Flag-dark:
-- nothing reads these until the companion flags are on. NOT applied to prod
-- (separate approval step).
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Weekly-goal defaults — spec line 365 (DEFAULT 3 meaningful practice days,
-- user-adjustable, sane bounds). Merged into the hatch-v1 config so the default
-- + bounds stay in DATA. Progress is never stored; it is computed at read time.
-- ---------------------------------------------------------------------------
UPDATE companion_reward_policy
   SET config = config || '{"weekly_goal":{"default_target":3,"min":1,"max":7}}'::jsonb
 WHERE version = 'hatch-v1';

-- ---------------------------------------------------------------------------
-- companion_weekly_goal — per-owner goal TARGET override only. Progress resets
-- weekly by construction (computed over the current week from evidence), earned
-- history remains in competency_evidence. There is deliberately NO progress or
-- streak column: a missed week stores nothing and penalises nothing (R2).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companion_weekly_goal (
  owner_user_id  TEXT PRIMARY KEY,                -- Clerk user id (A3)
  target         INT NOT NULL DEFAULT 3 CHECK (target BETWEEN 1 AND 7),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TRIGGER IF EXISTS trg_companion_weekly_goal_updated ON companion_weekly_goal;
CREATE TRIGGER trg_companion_weekly_goal_updated
  BEFORE UPDATE ON companion_weekly_goal
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ---------------------------------------------------------------------------
-- quest_definition — versioned quest catalog (spec §7.2). Public catalog (no
-- answer keys — objectives reference server-computed evidence, never solutions),
-- read-all for authenticated, mirroring competency_definition. PK (id, version)
-- keeps published versions immutable.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quest_definition (
  id                 TEXT NOT NULL,               -- stable quest id, e.g. 'watchtower'
  version            INT  NOT NULL DEFAULT 1,
  title_en           TEXT NOT NULL,
  title_ru           TEXT NOT NULL,
  title_kk           TEXT NOT NULL,
  desc_en            TEXT NOT NULL,
  desc_ru            TEXT NOT NULL,
  desc_kk            TEXT NOT NULL,
  region             TEXT,                         -- spec §7.1 region, e.g. 'watchtower'
  prerequisites      JSONB NOT NULL DEFAULT '[]'::jsonb,   -- quest ids required first
  objectives         JSONB NOT NULL DEFAULT '[]'::jsonb,   -- typed objective list (no solutions)
  reward_policy_key  TEXT NOT NULL DEFAULT 'chapter_first',-- companion_reward_policy key (reuse)
  replay_policy      TEXT NOT NULL DEFAULT 'once' CHECK (replay_policy IN ('once','repeatable')),
  publish_state      TEXT NOT NULL DEFAULT 'published'
                       CHECK (publish_state IN ('draft','published','archived')),
  sort_order         INT  NOT NULL DEFAULT 0,
  active             BOOLEAN NOT NULL DEFAULT true,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (id, version)
);

DROP TRIGGER IF EXISTS trg_quest_definition_updated ON quest_definition;
CREATE TRIGGER trg_quest_definition_updated
  BEFORE UPDATE ON quest_definition
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ---------------------------------------------------------------------------
-- quest_progress — per-owner quest state (A3). Owner-read; writes service-role.
-- UNIQUE(owner, quest_id, quest_version) ⇒ one progress/completion per owner per
-- published version (first-completion idempotency guard).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quest_progress (
  id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_user_id      TEXT NOT NULL,
  quest_id           TEXT NOT NULL,
  quest_version      INT  NOT NULL,
  state              TEXT NOT NULL DEFAULT 'available'
                       CHECK (state IN ('locked','available','active','objectives_complete','completed')),
  objective_progress JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at         TIMESTAMPTZ,
  completed_at       TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (owner_user_id, quest_id, quest_version)
);
CREATE INDEX IF NOT EXISTS idx_quest_progress_owner
  ON quest_progress (owner_user_id, quest_id);

DROP TRIGGER IF EXISTS trg_quest_progress_updated ON quest_progress;
CREATE TRIGGER trg_quest_progress_updated
  BEFORE UPDATE ON quest_progress
  FOR EACH ROW EXECUTE FUNCTION gamification_touch_updated_at();

-- ============================================================================
-- companion_complete_quest — atomic + idempotent quest-completion write.
-- Objectives are verified SERVER-SIDE (never a client flag): the Watchtower quest
-- is complete when ALL its learning nodes have a correct attempt — the same
-- COUNT DISTINCT computation as companion_complete_learning_node (Phase 4). The
-- reward reuses the chapter_first AMOUNT (passed in) but a DISTINCT idempotency
-- key (companion:quest:<owner>:<quest_version>), so repeat play regrants nothing.
-- ============================================================================
CREATE OR REPLACE FUNCTION companion_complete_quest(
  p_owner         TEXT,
  p_org           UUID,
  p_student       TEXT,
  p_quest_id      TEXT,
  p_quest_version INT,
  p_total_nodes   INT,
  p_reward_xp     NUMERIC,
  p_reward_coins  NUMERIC,
  p_reward_key    TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_completed    INT;
  v_objectives   BOOLEAN := false;
  v_reward_xp_id UUID;
  v_granted      BOOLEAN := false;
  v_state        TEXT;
BEGIN
  -- Serialize concurrent completion checks for this (owner, quest).
  PERFORM pg_advisory_xact_lock(hashtext('companion:quest:' || p_owner || ':' || p_quest_id));

  -- Authoritative objective check: distinct Watchtower learning families this
  -- owner has answered correctly (identical to the chapter computation, §7.3).
  SELECT count(DISTINCT td.family) INTO v_completed
    FROM task_attempt ta
    JOIN task_assignment asg ON asg.id = ta.assignment_id
    JOIN task_definition  td ON td.id  = ta.task_id
   WHERE ta.owner_user_id = p_owner
     AND ta.correct = true
     AND asg.mode = 'learning';

  v_objectives := v_completed >= p_total_nodes;

  -- Ensure a progress row exists (idempotent).
  INSERT INTO quest_progress (owner_user_id, quest_id, quest_version, state, objective_progress)
  VALUES (p_owner, p_quest_id, p_quest_version, 'available',
          jsonb_build_object('watchtower',
            jsonb_build_object('done', v_completed, 'total', p_total_nodes)))
  ON CONFLICT (owner_user_id, quest_id, quest_version) DO UPDATE
    SET objective_progress = jsonb_build_object('watchtower',
          jsonb_build_object('done', v_completed, 'total', p_total_nodes));

  IF v_objectives THEN
    UPDATE quest_progress
       SET state        = 'completed',
           completed_at = COALESCE(completed_at, now())
     WHERE owner_user_id = p_owner
       AND quest_id      = p_quest_id
       AND quest_version = p_quest_version;

    -- First completion → reward exactly once (globally-UNIQUE idempotency key).
    IF p_reward_xp > 0 THEN
      INSERT INTO xp_ledger (
        organization_id, student_id, amount, reason, wins,
        source_type, source_id, idempotency_key, occurred_at
      ) VALUES (
        p_org, p_student, p_reward_xp, 'companion_quest_completion', NULL,
        'companion', p_quest_id, p_reward_key, now()
      )
      ON CONFLICT (idempotency_key) DO NOTHING
      RETURNING id INTO v_reward_xp_id;

      IF v_reward_xp_id IS NOT NULL THEN
        v_granted := true;
        INSERT INTO coin_ledger (
          organization_id, student_id, amount, source, source_id, idempotency_key, occurred_at
        ) VALUES (
          p_org, p_student, p_reward_coins, 'chapter_completion', p_quest_id, p_reward_key, now()
        )
        ON CONFLICT (idempotency_key) DO NOTHING;

        INSERT INTO domain_event (owner_user_id, event_type, payload)
        VALUES (
          p_owner, 'companion_quest_completed',
          jsonb_build_object('quest_id', p_quest_id, 'quest_version', p_quest_version,
                             'nodes', p_total_nodes)
        );

        UPDATE player_gamification
           SET xp_total     = (SELECT COALESCE(SUM(amount), 0) FROM xp_ledger
                                 WHERE organization_id = p_org AND student_id = p_student),
               coin_balance = GREATEST(0, (SELECT COALESCE(SUM(amount), 0) FROM coin_ledger
                                 WHERE organization_id = p_org AND student_id = p_student)),
               updated_at   = now()
         WHERE organization_id = p_org AND student_id = p_student;
        IF NOT FOUND THEN
          INSERT INTO player_gamification (organization_id, student_id, xp_total, coin_balance)
            VALUES (p_org, p_student, GREATEST(0, p_reward_xp), GREATEST(0, p_reward_coins))
            ON CONFLICT (organization_id, student_id) DO NOTHING;
        END IF;
      END IF;
    END IF;
  END IF;

  SELECT state INTO v_state FROM quest_progress
   WHERE owner_user_id = p_owner AND quest_id = p_quest_id AND quest_version = p_quest_version;

  RETURN jsonb_build_object(
    'state', v_state,
    'objectives_complete', v_objectives,
    'completed_count', v_completed,
    'total', p_total_nodes,
    'reward_granted', v_granted,
    'xp', CASE WHEN v_granted THEN p_reward_xp ELSE 0 END,
    'coins', CASE WHEN v_granted THEN p_reward_coins ELSE 0 END
  );
END;
$$;

REVOKE ALL ON FUNCTION companion_complete_quest(
  TEXT, UUID, TEXT, TEXT, INT, INT, NUMERIC, NUMERIC, TEXT
) FROM PUBLIC, anon, authenticated;

-- ============================================================================
-- Row Level Security
-- ============================================================================

-- quest_definition: public catalog — read-all for authenticated (no solutions).
ALTER TABLE quest_definition ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON quest_definition FROM anon, authenticated;
GRANT SELECT ON quest_definition TO authenticated;
DROP POLICY IF EXISTS "read_all" ON quest_definition;
CREATE POLICY "read_all" ON quest_definition
  FOR SELECT TO authenticated USING (true);

-- Owner-read tables: authenticated SELECT only own rows; writes service-role.
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['companion_weekly_goal','quest_progress'] LOOP
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

-- ============================================================================
-- Seed the one pilot quest: the Watchtower chapter wrapped as a quest (spec
-- §7.2 minimal). Objective = complete all six Watchtower learning nodes; reward
-- reuses the chapter_first policy key. NO cooperative/expedition quests.
-- ============================================================================
INSERT INTO quest_definition
  (id, version, title_en, title_ru, title_kk, desc_en, desc_ru, desc_kk,
   region, prerequisites, objectives, reward_policy_key, replay_policy, publish_state, sort_order)
VALUES
  ('watchtower', 1,
   'The Watchtower Quest', 'Квест «Дозорная башня»', 'Күзет мұнарасы тапсырмасы',
   'Complete all six Watchtower challenges to finish the quest.',
   'Пройдите все шесть испытаний Дозорной башни, чтобы завершить квест.',
   'Тапсырманы аяқтау үшін Күзет мұнарасының алты сынағын орындаңыз.',
   'watchtower',
   '[]'::jsonb,
   '[{"type":"complete_task","chapter":"watchtower","nodes":["W01","W02","W03","W04","W05","W06"]}]'::jsonb,
   'chapter_first', 'once', 'published', 1)
ON CONFLICT (id, version) DO NOTHING;

COMMIT;

-- ============================================================================
-- ROLLBACK (manual) — preserves earned identity/progress/inventory/ledger:
--   DROP FUNCTION IF EXISTS companion_complete_quest(
--     TEXT, UUID, TEXT, TEXT, INT, INT, NUMERIC, NUMERIC, TEXT);
--   DROP TABLE IF EXISTS quest_progress, quest_definition, companion_weekly_goal CASCADE;
--   UPDATE companion_reward_policy SET config = config - 'weekly_goal' WHERE version = 'hatch-v1';
--   -- xp_ledger / coin_ledger rows are append-only and intentionally retained.
-- ============================================================================
