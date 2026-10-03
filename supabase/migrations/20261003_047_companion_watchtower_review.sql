-- ============================================================================
-- 20261003_047_companion_watchtower_review.sql
-- Companion Phase 4 — Watchtower chapter + pull-based SM-2 review.
--
-- Builds on migrations 044 (foundations), 045 (assessment), 046 (hatch). Adds:
--  • review_ladder in the hatch-v1 reward policy config (spec §6.3 DEFAULT
--    intervals 1/3/7/14) — the ladder lives in DATA, never hardcoded in code.
--  • companion_record_review() — ONE atomic, idempotent SECURITY DEFINER RPC
--    that records a review attempt + evidence (kind='review'), advances the
--    mastery_state scheduler to the TS-computed rung (interval_days +
--    next_review_at — the clock is injectable in TS so unit tests can move it),
--    and grants the `due_review` reward (spec §6.2) exactly once per due
--    occurrence via a companion:review:<owner>:<competency>:<marker> key.
--  • companion_complete_learning_node() — ONE atomic, idempotent SECURITY
--    DEFINER RPC that records a learning-node attempt + evidence
--    (kind='learning'), and when ALL Watchtower nodes have a correct attempt,
--    grants the `chapter_first` reward (spec §6.2) exactly once via
--    companion:chapter:<owner>:watchtower (source 'chapter_completion', already
--    allowed by the 044 CHECK) + one companion_chapter_completed domain_event.
--    Completion is computed server-side from attempts — never a client flag.
--  • 6 Watchtower learning nodes (W01–W06) in task_definition with mode='learning'
--    (storage pattern mirrors the 045 assessment pool: FEN + prompt ×3 locales +
--    solution JSONB + hints JSONB + validator). Every FEN/solution is
--    chess.js-verified (see companion/__tests__/watchtower-content.test.ts).
--    Reuses the seeded competency catalog (H_*) as the FK/scheduling bucket —
--    the Watchtower chapter is post-hatch practice (attacks/defenders/undefended
--    pieces/safe captures), the competency code is the review-scheduling bucket.
--
-- No new coin_ledger.source values — `due_review` and `chapter_completion` are
-- already allowed by the 044 CHECK. Study: companion_record_attempt (045) +
-- hatch_companion (046) for house style (advisory lock + idempotency keys).
--
-- Idempotent: safe to re-run (ON CONFLICT DO NOTHING). Flag-dark: nothing reads
-- this until the flag is on. NOT applied to prod (separate approval step).
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Review ladder — spec §6.3 DEFAULT intervals (1, 3, 7, 14 days). Merged into
-- the existing hatch-v1 config so the ladder stays in DATA, not code. A failed
-- or assisted review resets to the first rung (handled in the TS scheduler).
-- ---------------------------------------------------------------------------
UPDATE companion_reward_policy
   SET config = config || '{"review_ladder":[1,3,7,14]}'::jsonb
 WHERE version = 'hatch-v1';

-- ============================================================================
-- companion_record_review — atomic + idempotent review-result write.
-- Validation (chess.js) and scheduling (SM-2 ladder with an injectable clock)
-- happen in the Next route/pure-rules; this RPC trusts the route's computed
-- correctness + rung and owns ALL persistence in one txn.
--
-- Idempotency: (1) task_attempt.submission_key UNIQUE dedups a double-submit;
-- (2) the reward idempotency_key (companion:review:<owner>:<competency>:<marker>)
-- is globally UNIQUE in the ledgers, so the due_review reward is granted at most
-- once per due occurrence (the marker is the next_review_at that became due, or
-- 'initial' for the first-ever review).
-- ============================================================================
CREATE OR REPLACE FUNCTION companion_record_review(
  p_owner           TEXT,
  p_org             UUID,
  p_student         TEXT,
  p_assignment      UUID,
  p_task            UUID,
  p_competency      TEXT,
  p_submission      JSONB,
  p_correct         BOOLEAN,
  p_assistance_used BOOLEAN,
  p_submission_key  TEXT,
  p_policy_version  TEXT,
  p_interval_days   INT,
  p_next_review_at  TIMESTAMPTZ,
  p_reward_xp       NUMERIC,
  p_reward_coins    NUMERIC,
  p_reward_key      TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_attempt_id    UUID;
  v_assist        BOOLEAN;
  v_reward_xp_id  UUID;
  v_granted       BOOLEAN := false;
  v_times_correct INT;
  v_prev          task_attempt%ROWTYPE;
BEGIN
  -- Serialize concurrent reviews for this (owner, competency).
  PERFORM pg_advisory_xact_lock(hashtext('companion:review:' || p_owner || ':' || p_competency));

  v_assist := COALESCE(p_assistance_used, false);

  INSERT INTO task_attempt (
    assignment_id, owner_user_id, task_id, submission, correct,
    first_response, assistance_used, submission_key
  ) VALUES (
    p_assignment, p_owner, p_task, p_submission, p_correct,
    true, v_assist, p_submission_key
  )
  ON CONFLICT (submission_key) DO NOTHING
  RETURNING id INTO v_attempt_id;

  -- Replay (same submission_key): return the stored verdict, write nothing new.
  IF v_attempt_id IS NULL THEN
    SELECT * INTO v_prev FROM task_attempt WHERE submission_key = p_submission_key;
    SELECT times_correct INTO v_times_correct FROM mastery_state
      WHERE owner_user_id = p_owner AND competency_code = p_competency;
    RETURN jsonb_build_object(
      'status', 'replayed',
      'correct', v_prev.correct,
      'assistance_used', v_prev.assistance_used,
      'interval_days', p_interval_days,
      'next_review_at', p_next_review_at,
      'times_correct', COALESCE(v_times_correct, 0),
      'reward_granted', false, 'xp', 0, 'coins', 0
    );
  END IF;

  -- Append-only evidence row (review kind) under the versioned policy.
  INSERT INTO competency_evidence (
    owner_user_id, competency_code, kind, source_attempt_id,
    correct, assistance_used, policy_version
  ) VALUES (
    p_owner, p_competency, 'review', v_attempt_id,
    p_correct, v_assist, p_policy_version
  );

  -- Advance the scheduler to the TS-computed rung. The mastery row exists after
  -- hatch; an INSERT fallback keeps the RPC safe for a first-ever review.
  INSERT INTO mastery_state (
    owner_user_id, competency_code, interval_days, next_review_at,
    times_trained, times_correct, last_trained_at, policy_version
  ) VALUES (
    p_owner, p_competency, p_interval_days, p_next_review_at,
    1, CASE WHEN p_correct THEN 1 ELSE 0 END, now(), p_policy_version
  )
  ON CONFLICT (owner_user_id, competency_code) DO UPDATE
    SET interval_days   = p_interval_days,
        next_review_at  = p_next_review_at,
        times_trained   = mastery_state.times_trained + 1,
        times_correct   = mastery_state.times_correct + CASE WHEN p_correct THEN 1 ELSE 0 END,
        last_trained_at = now()
  RETURNING times_correct INTO v_times_correct;

  UPDATE task_assignment
     SET status = CASE WHEN p_correct THEN 'passed' ELSE 'failed' END
   WHERE id = p_assignment;

  -- Independent (unassisted, correct) due review → reward, once per occurrence.
  IF p_correct AND NOT v_assist AND p_reward_xp > 0 THEN
    INSERT INTO xp_ledger (
      organization_id, student_id, amount, reason, wins,
      source_type, source_id, idempotency_key, occurred_at
    ) VALUES (
      p_org, p_student, p_reward_xp, 'companion_due_review', NULL,
      'companion', p_competency, p_reward_key, now()
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING id INTO v_reward_xp_id;

    IF v_reward_xp_id IS NOT NULL THEN
      v_granted := true;
      INSERT INTO coin_ledger (
        organization_id, student_id, amount, source, source_id, idempotency_key, occurred_at
      ) VALUES (
        p_org, p_student, p_reward_coins, 'due_review', p_competency, p_reward_key, now()
      )
      ON CONFLICT (idempotency_key) DO NOTHING;

      INSERT INTO domain_event (owner_user_id, event_type, payload)
      VALUES (
        p_owner, 'companion_review_completed',
        jsonb_build_object('competency_id', p_competency, 'interval_days', p_interval_days,
                           'policy_version', p_policy_version)
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

  RETURN jsonb_build_object(
    'status', 'ok',
    'correct', p_correct,
    'assistance_used', v_assist,
    'interval_days', p_interval_days,
    'next_review_at', p_next_review_at,
    'times_correct', v_times_correct,
    'reward_granted', v_granted,
    'xp', CASE WHEN v_granted THEN p_reward_xp ELSE 0 END,
    'coins', CASE WHEN v_granted THEN p_reward_coins ELSE 0 END
  );
END;
$$;

REVOKE ALL ON FUNCTION companion_record_review(
  TEXT, UUID, TEXT, UUID, UUID, TEXT, JSONB, BOOLEAN, BOOLEAN, TEXT, TEXT, INT, TIMESTAMPTZ, NUMERIC, NUMERIC, TEXT
) FROM PUBLIC, anon, authenticated;

-- ============================================================================
-- companion_complete_learning_node — atomic + idempotent learning-node write +
-- chapter-completion reward. Validation (chess.js) happens in the Next route;
-- this RPC records the attempt/evidence and grants the chapter reward exactly
-- once when ALL Watchtower learning nodes have a correct attempt.
--
-- Completion is computed server-side (COUNT DISTINCT family of correct learning
-- attempts) — never a client-asserted flag (spec §16 T01/T02).
-- ============================================================================
CREATE OR REPLACE FUNCTION companion_complete_learning_node(
  p_owner          TEXT,
  p_org            UUID,
  p_student        TEXT,
  p_assignment     UUID,
  p_task           UUID,
  p_competency     TEXT,
  p_submission     JSONB,
  p_correct        BOOLEAN,
  p_submission_key TEXT,
  p_policy_version TEXT,
  p_total_nodes    INT,
  p_reward_xp      NUMERIC,
  p_reward_coins   NUMERIC,
  p_reward_key     TEXT
) RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_attempt_id    UUID;
  v_completed     INT;
  v_chapter_done  BOOLEAN := false;
  v_reward_xp_id  UUID;
  v_granted       BOOLEAN := false;
BEGIN
  -- Serialize concurrent node completions for this owner (chapter reward lock).
  PERFORM pg_advisory_xact_lock(hashtext('companion:chapter:' || p_owner || ':watchtower'));

  INSERT INTO task_attempt (
    assignment_id, owner_user_id, task_id, submission, correct,
    first_response, assistance_used, submission_key
  ) VALUES (
    p_assignment, p_owner, p_task, p_submission, p_correct,
    true, false, p_submission_key
  )
  ON CONFLICT (submission_key) DO NOTHING
  RETURNING id INTO v_attempt_id;

  -- New attempt ⇒ record evidence + update the assignment status.
  IF v_attempt_id IS NOT NULL THEN
    INSERT INTO competency_evidence (
      owner_user_id, competency_code, kind, source_attempt_id,
      correct, assistance_used, policy_version
    ) VALUES (
      p_owner, p_competency, 'learning', v_attempt_id,
      p_correct, false, p_policy_version
    );
    UPDATE task_assignment
       SET status = CASE WHEN p_correct THEN 'passed' ELSE 'failed' END
     WHERE id = p_assignment;
  END IF;

  -- Chapter completion is authoritative: how many DISTINCT Watchtower learning
  -- nodes have at least one CORRECT attempt by this owner.
  SELECT count(DISTINCT td.family) INTO v_completed
    FROM task_attempt ta
    JOIN task_assignment asg ON asg.id = ta.assignment_id
    JOIN task_definition  td ON td.id  = ta.task_id
   WHERE ta.owner_user_id = p_owner
     AND ta.correct = true
     AND asg.mode = 'learning';

  v_chapter_done := v_completed >= p_total_nodes;

  -- First full chapter completion → reward, exactly once (UNIQUE key).
  IF v_chapter_done AND p_reward_xp > 0 THEN
    INSERT INTO xp_ledger (
      organization_id, student_id, amount, reason, wins,
      source_type, source_id, idempotency_key, occurred_at
    ) VALUES (
      p_org, p_student, p_reward_xp, 'companion_chapter_completion', NULL,
      'companion', 'watchtower', p_reward_key, now()
    )
    ON CONFLICT (idempotency_key) DO NOTHING
    RETURNING id INTO v_reward_xp_id;

    IF v_reward_xp_id IS NOT NULL THEN
      v_granted := true;
      INSERT INTO coin_ledger (
        organization_id, student_id, amount, source, source_id, idempotency_key, occurred_at
      ) VALUES (
        p_org, p_student, p_reward_coins, 'chapter_completion', 'watchtower', p_reward_key, now()
      )
      ON CONFLICT (idempotency_key) DO NOTHING;

      INSERT INTO domain_event (owner_user_id, event_type, payload)
      VALUES (
        p_owner, 'companion_chapter_completed',
        jsonb_build_object('chapter', 'watchtower', 'nodes', p_total_nodes,
                           'policy_version', p_policy_version)
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

  RETURN jsonb_build_object(
    'status', CASE WHEN v_attempt_id IS NULL THEN 'replayed' ELSE 'ok' END,
    'correct', p_correct,
    'completed_count', v_completed,
    'total', p_total_nodes,
    'chapter_complete', v_chapter_done,
    'reward_granted', v_granted,
    'xp', CASE WHEN v_granted THEN p_reward_xp ELSE 0 END,
    'coins', CASE WHEN v_granted THEN p_reward_coins ELSE 0 END
  );
END;
$$;

REVOKE ALL ON FUNCTION companion_complete_learning_node(
  TEXT, UUID, TEXT, UUID, UUID, TEXT, JSONB, BOOLEAN, TEXT, TEXT, INT, NUMERIC, NUMERIC, TEXT
) FROM PUBLIC, anon, authenticated;

-- ============================================================================
-- Watchtower chapter — six learning nodes (spec §7.3 W01–W06). mode='learning'.
-- Reuses the seeded competency catalog (H_*) as the FK/review-scheduling bucket.
-- Validators: 'squares' (set-membership: attackers/defenders/undefended target)
-- and 'move' (a legal, safe capture). Every FEN/solution chess.js-verified.
-- Re-runnable via the uq_task_definition_comp_family index from migration 045.
-- ============================================================================
INSERT INTO task_definition
  (competency_code, family, mode, fen, prompt_en, prompt_ru, prompt_kk, solution, validator, hints)
VALUES
  ('H_ROOK', 'W01', 'learning',
   '4k3/r7/8/8/8/8/8/R1B1K3 w - - 0 1',
   'Which of your white pieces attacks the black rook on a7? Select it.',
   'Какая из ваших белых фигур атакует чёрную ладью на a7? Выберите её.',
   'Ақ фигураларыңыздың қайсысы a7 тұрған қара тураға шабуыл жасайды? Таңдаңыз.',
   '{"squares":["a1"]}'::jsonb, 'squares',
   '[{"en":"An attacker can move to the target square in one move.","ru":"Атакующая фигура может пойти на поле цели за один ход.","kk":"Шабуылдаушы фигура нысана алаңына бір жүрісте бара алады."}]'::jsonb),

  ('H_BISHOP', 'W02', 'learning',
   '4k3/8/8/4P3/3P4/8/8/4R1K1 w - - 0 1',
   'Which white pieces defend the pawn on e5? Select all of them.',
   'Какие белые фигуры защищают пешку на e5? Выберите все.',
   'e5 тұрған сарбазды қай ақ фигуралар қорғайды? Барлығын таңдаңыз.',
   '{"squares":["d4","e1"]}'::jsonb, 'squares',
   '[{"en":"A defender could recapture on the square if the piece were taken.","ru":"Защитник может взять на этом поле, если фигуру побьют.","kk":"Қорғаушы фигура алынса, сол алаңда кері ала алады."}]'::jsonb),

  ('H_KNIGHT', 'W03', 'learning',
   '4k3/1p6/2b4n/8/8/8/8/4K3 w - - 0 1',
   'One black piece has no defender. Select the undefended piece.',
   'Одна чёрная фигура не защищена. Выберите незащищённую фигуру.',
   'Бір қара фигура қорғалмаған. Қорғалмаған фигураны таңдаңыз.',
   '{"squares":["h6"]}'::jsonb, 'squares',
   '[{"en":"An undefended piece has no friendly piece that could recapture.","ru":"У незащищённой фигуры нет своей фигуры, которая могла бы отыграть.","kk":"Қорғалмаған фигураның кері ала алатын досы жоқ."}]'::jsonb),

  ('H_QUEEN', 'W04', 'learning',
   '4k3/p7/8/8/8/8/8/R3K3 w - - 0 1',
   'Capture the undefended black pawn safely with your rook.',
   'Безопасно побейте незащищённую чёрную пешку ладьёй.',
   'Қорғалмаған қара сарбазды турамен қауіпсіз алыңыз.',
   '{"moves":["a1a7"]}'::jsonb, 'move',
   '[{"en":"Take a piece that nothing can recapture.","ru":"Берите фигуру, которую нечем отыграть.","kk":"Ешкім кері ала алмайтын фигураны алыңыз."}]'::jsonb),

  ('H_KING', 'W05', 'learning',
   '4k3/8/n7/8/8/8/8/4KB2 w - - 0 1',
   'Watchtower trial: capture the undefended knight with your bishop.',
   'Испытание дозорной башни: побейте незащищённого коня слоном.',
   'Күзет мұнарасының сынағы: қорғалмаған атты пілмен алыңыз.',
   '{"moves":["f1a6"]}'::jsonb, 'move',
   '[{"en":"Follow the diagonal all the way to the loose piece.","ru":"Идите по диагонали прямо к незащищённой фигуре.","kk":"Диагональ бойымен бос фигураға дейін жүріңіз."}]'::jsonb),

  ('H_CHECK', 'W06', 'learning',
   '4k3/8/8/3r4/8/8/8/3QK3 w - - 0 1',
   'Later review: capture the undefended black rook with your queen.',
   'Отложенный повтор: побейте незащищённую чёрную ладью ферзём.',
   'Кейінгі қайталау: қорғалмаған қара тураны уәзірмен алыңыз.',
   '{"moves":["d1d5"]}'::jsonb, 'move',
   '[{"en":"The queen can travel straight up the file to the rook.","ru":"Ферзь может пройти прямо по вертикали к ладье.","kk":"Уәзір тік сызықпен тура тураға дейін жүре алады."}]'::jsonb)
ON CONFLICT (competency_code, family) DO NOTHING;

COMMIT;

-- ============================================================================
-- ROLLBACK (manual):
--   DELETE FROM task_definition WHERE family IN ('W01','W02','W03','W04','W05','W06');
--   DROP FUNCTION IF EXISTS companion_complete_learning_node(
--     TEXT, UUID, TEXT, UUID, UUID, TEXT, JSONB, BOOLEAN, TEXT, TEXT, INT, NUMERIC, NUMERIC, TEXT);
--   DROP FUNCTION IF EXISTS companion_record_review(
--     TEXT, UUID, TEXT, UUID, UUID, TEXT, JSONB, BOOLEAN, BOOLEAN, TEXT, TEXT, INT, TIMESTAMPTZ, NUMERIC, NUMERIC, TEXT);
--   UPDATE companion_reward_policy SET config = config - 'review_ladder' WHERE version = 'hatch-v1';
-- ============================================================================
