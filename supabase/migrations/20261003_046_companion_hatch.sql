-- ============================================================================
-- 20261003_046_companion_hatch.sql
-- Companion Phase 3 — Hatch (.ralph/companion-phase3-task.md).
--
-- Builds on migrations 044 (foundations) + 045 (assessment). Adds:
--  • hatch_companion() — ONE atomic, idempotent SECURITY DEFINER RPC that:
--      1. re-verifies hatch readiness from AUTHORITATIVE evidence (every active
--         competency demonstrated via mastery_state.times_correct >= target) —
--         never trusts a client "ready" flag (spec §12.4, §16 T01/T02);
--      2. transitions (or creates) the companion row egg → hatched, locking in
--         species (chosen egg, else the default) + chosen name + hatched_at;
--      3. grants the one-time starter accessory entitlement (spec §9.1 hatch
--         grant) — exactly once via player_items UNIQUE(org,student,item);
--      4. grants the hatch reward (XP/coins) into xp_ledger/coin_ledger with a
--         companion:* namespaced idempotency key — exactly once;
--      5. appends one companion_hatched domain_event.
--    Idempotent: calling twice = one companion, one entitlement, one grant, one
--    event (advisory lock + early already-hatched return + UNIQUE keys).
--  • a 'hatch' entry in the hatch-v1 reward policy (spec §6.2 — reward in DATA).
--  • one starter-accessory item seeded for the chess-empire org.
--
-- No new sources are added to coin_ledger.source — the hatch reward reuses the
-- 'chapter_completion' source (the Hatchery region completes at hatch) already
-- allowed by the 044 CHECK. Study: spend_coins (034) + companion_record_attempt
-- (045) for house style.
--
-- Idempotent: safe to re-run. Flag-dark: nothing reads this until the flag is on.
-- NOT applied to prod (separate approval step).
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Reward policy — add the hatch grant (spec §6.2: a region completion is 50/20).
-- Merged into the existing hatch-v1 config so values stay in DATA, not code.
-- ---------------------------------------------------------------------------
UPDATE companion_reward_policy
   SET config = config || '{"hatch":{"xp":50,"coins":20}}'::jsonb
 WHERE version = 'hatch-v1';

-- ---------------------------------------------------------------------------
-- Starter accessory — the single free "basic accessory" granted at hatch
-- (spec §9.1). Seeded for chess-empire only; kind 'default' (free, not buyable).
-- ---------------------------------------------------------------------------
INSERT INTO items
  (organization_id, sku, slot, rarity, kind, price_coins,
   name_en, name_ru, name_kk, art_url, is_placeholder_art, sort_order, acquisition_note)
SELECT o.id, 'companion_starter', 'neck', 'common', 'default', NULL,
  'Explorer''s Scarf', 'Шарф исследователя', 'Зерттеуші орамалы',
  '/gamification/companion-starter.svg', true, 100,
  'Free starter accessory granted once at companion hatch'
FROM organizations o
WHERE o.slug = 'chess-empire'
ON CONFLICT (organization_id, sku) DO NOTHING;

-- ============================================================================
-- hatch_companion — the atomic, idempotent hatch transaction (spec §12.4).
-- Readiness is re-checked here from mastery_state (the authoritative evidence
-- written only by companion_record_attempt); the caller's view is never trusted.
-- ============================================================================
CREATE OR REPLACE FUNCTION hatch_companion(
  p_owner           TEXT,
  p_org             UUID,
  p_student         TEXT,
  p_name            TEXT,
  p_species_default TEXT,
  p_mastery_target  INT,
  p_reward_xp       NUMERIC,
  p_reward_coins    NUMERIC,
  p_reward_key      TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_existing        companion%ROWTYPE;
  v_total           INT;
  v_demo            INT;
  v_species         TEXT;
  v_name            TEXT;
  v_hatched_at      TIMESTAMPTZ;
  v_companion_id    UUID;
  v_starter_item    UUID;
  v_starter_granted BOOLEAN := false;
  v_reward_xp_id    UUID;
  v_granted         BOOLEAN := false;
BEGIN
  -- Serialize concurrent hatch attempts for this owner (spec §12.4: lock starter).
  PERFORM pg_advisory_xact_lock(hashtext('companion:hatch:' || p_owner));

  SELECT * INTO v_existing FROM companion WHERE owner_user_id = p_owner;

  -- Idempotent: already hatched ⇒ return the same companion, grant nothing new.
  IF FOUND AND v_existing.stage = 'hatched' THEN
    RETURN jsonb_build_object(
      'status', 'already_hatched',
      'companion', jsonb_build_object(
        'species', v_existing.species, 'name', v_existing.name,
        'stage', v_existing.stage, 'hatched_at', v_existing.hatched_at),
      'reward_granted', false, 'xp', 0, 'coins', 0, 'starter_granted', false
    );
  END IF;

  -- Authoritative evidence: EVERY active competency demonstrated (mirrors the
  -- pure isHatchReady rule in state.ts). Any missing ⇒ denied, nothing changes.
  SELECT count(*) INTO v_total FROM competency_definition WHERE active = true;
  SELECT count(*) INTO v_demo
    FROM competency_definition cd
    JOIN mastery_state ms
      ON ms.owner_user_id = p_owner AND ms.competency_code = cd.code
   WHERE cd.active = true AND ms.times_correct >= p_mastery_target;

  IF v_total = 0 OR v_demo < v_total THEN
    RETURN jsonb_build_object('status', 'not_ready', 'demonstrated', v_demo, 'required', v_total);
  END IF;

  -- Species: preserve a pre-hatch chosen egg, else the default ('fox'). Locked in
  -- with the hatch (spec §3.3: immutable species after hatch).
  v_species := COALESCE(NULLIF(v_existing.species, ''), p_species_default);

  INSERT INTO companion (owner_user_id, species, name, stage, hatched_at)
    VALUES (p_owner, v_species, p_name, 'hatched', now())
  ON CONFLICT (owner_user_id) DO UPDATE
    SET species    = COALESCE(NULLIF(companion.species, ''), EXCLUDED.species),
        name       = EXCLUDED.name,
        stage      = 'hatched',
        hatched_at = now()
  RETURNING id, species, name, hatched_at
    INTO v_companion_id, v_species, v_name, v_hatched_at;

  -- Starter accessory entitlement — one free basic accessory (spec §9.1), granted
  -- exactly once (UNIQUE(org,student,item) makes a re-run a no-op).
  SELECT id INTO v_starter_item FROM items
    WHERE organization_id = p_org AND sku = 'companion_starter' AND available = true
    LIMIT 1;
  IF v_starter_item IS NOT NULL THEN
    INSERT INTO player_items (organization_id, student_id, item_id, acquired_via)
      VALUES (p_org, p_student, v_starter_item, 'admin_grant')
    ON CONFLICT (organization_id, student_id, item_id) DO NOTHING;
    v_starter_granted := true;
  END IF;

  -- Hatch reward → one XP grant + one coin grant, keyed by the companion:* key so
  -- a concurrent/double hatch can never double-pay (belt-and-suspenders on top of
  -- the already-hatched early return above).
  IF p_reward_xp > 0 THEN
    INSERT INTO xp_ledger (
      organization_id, student_id, amount, reason, wins,
      source_type, source_id, idempotency_key, occurred_at
    ) VALUES (
      p_org, p_student, p_reward_xp, 'companion_hatch', NULL,
      'companion', p_owner, p_reward_key, now()
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING id INTO v_reward_xp_id;

    IF v_reward_xp_id IS NOT NULL THEN
      v_granted := true;
      INSERT INTO coin_ledger (
        organization_id, student_id, amount, source, source_id, idempotency_key, occurred_at
      ) VALUES (
        p_org, p_student, p_reward_coins, 'chapter_completion', p_owner, p_reward_key, now()
      )
      ON CONFLICT (idempotency_key) DO NOTHING;

      -- Refresh the read model (authoritative balance is SUM of the ledgers).
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

  -- One audit event per hatch (reachable only on the first hatch — the already-
  -- hatched path returned above, and the advisory lock serializes concurrent calls).
  INSERT INTO domain_event (owner_user_id, event_type, payload)
  VALUES (
    p_owner, 'companion_hatched',
    jsonb_build_object(
      'species', v_species,
      'policy_version', 'hatch-v1',
      'starter_item', v_starter_item)
  );

  RETURN jsonb_build_object(
    'status', 'ok',
    'companion', jsonb_build_object(
      'species', v_species, 'name', v_name, 'stage', 'hatched', 'hatched_at', v_hatched_at),
    'reward_granted', v_granted,
    'xp', CASE WHEN v_granted THEN p_reward_xp ELSE 0 END,
    'coins', CASE WHEN v_granted THEN p_reward_coins ELSE 0 END,
    'starter_granted', v_starter_granted
  );
END;
$$;

REVOKE ALL ON FUNCTION hatch_companion(
  TEXT, UUID, TEXT, TEXT, TEXT, INT, NUMERIC, NUMERIC, TEXT
) FROM PUBLIC, anon, authenticated;

COMMIT;

-- ============================================================================
-- ROLLBACK (manual):
--   DROP FUNCTION IF EXISTS hatch_companion(TEXT, UUID, TEXT, TEXT, TEXT, INT, NUMERIC, NUMERIC, TEXT);
--   DELETE FROM items WHERE sku = 'companion_starter';
--   UPDATE companion_reward_policy SET config = config - 'hatch' WHERE version = 'hatch-v1';
-- ============================================================================
