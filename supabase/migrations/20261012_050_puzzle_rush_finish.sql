-- ============================================================================
-- 20261012_050_puzzle_rush_finish.sql
-- Puzzle Rush instant moves (plan v2) — record a client-played run in one call.
--
-- The run now lives entirely in the client (§7.9 server validation dropped:
-- cheating is a non-issue). Flask recomputes score / strikes / streaks from the
-- attempts and calls puzzle_rush_finish_run(payload) once, so the whole write is
-- a single round trip to Postgres:
--
--   payload = {
--     run:      { id, user_id, display_name, mode, seed, started_at, deadline_at,
--                 ended_at, end_reason, duration_ms, score, strikes,
--                 current_streak, longest_streak, highest_solved_rating,
--                 avg_ms_per_puzzle, puzzle_count },
--     attempts: [{ idx, puzzle_id, puzzle_rating, result, user_moves,
--                  served_at, answered_at, ms }],
--     periods:  { daily, weekly }   -- UTC starts of the caller's local day / week
--   }
--
-- Inserts the (already ended) run + attempts, upserts the personal best (ties
-- keep the earlier run, same as 049), and returns
--   { status: created|duplicate|conflict, run: {...stored stats},
--     personal_rank, global_rank: { daily, weekly, all } }
-- Idempotent on run.id: a retry returns the stored row's result ("duplicate");
-- the same id from a different user is a "conflict" and writes nothing.
-- Ranks use the same rules as services/puzzle_rush.py (personal_rank,
-- global_rank).
--
-- Additive: function only, no table changes. Service-role only. NOT applied to
-- prod (separate approval step); Flask returns 503 finish_unavailable until it is.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION puzzle_rush_finish_run(payload JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  r         JSONB := payload->'run';
  v_id      UUID  := (r->>'id')::uuid;
  v_user    TEXT  := r->>'user_id';
  v_row     puzzle_rush_runs%ROWTYPE;
  v_status  TEXT  := 'created';
BEGIN
  IF v_user IS NULL THEN
    RAISE EXCEPTION 'puzzle_rush_finish_run: run.user_id is required';
  END IF;

  INSERT INTO puzzle_rush_runs (
    id, user_id, display_name, mode, seed, started_at, deadline_at,
    last_activity_at, ended_at, end_reason, duration_ms, score, strikes,
    current_streak, longest_streak, highest_solved_rating, avg_ms_per_puzzle,
    puzzle_count
  ) VALUES (
    v_id, v_user, r->>'display_name', r->>'mode', r->>'seed',
    (r->>'started_at')::timestamptz, (r->>'deadline_at')::timestamptz,
    (r->>'ended_at')::timestamptz, (r->>'ended_at')::timestamptz, r->>'end_reason',
    (r->>'duration_ms')::int, (r->>'score')::int, (r->>'strikes')::int,
    (r->>'current_streak')::int, (r->>'longest_streak')::int,
    (r->>'highest_solved_rating')::int, (r->>'avg_ms_per_puzzle')::int,
    (r->>'puzzle_count')::int
  )
  ON CONFLICT (id) DO NOTHING
  RETURNING * INTO v_row;

  IF NOT FOUND THEN
    SELECT * INTO v_row FROM puzzle_rush_runs WHERE id = v_id;
    IF v_row.user_id IS DISTINCT FROM v_user THEN
      RETURN jsonb_build_object('status', 'conflict');
    END IF;
    v_status := 'duplicate';
  ELSE
    INSERT INTO puzzle_rush_attempts (
      run_id, idx, puzzle_id, puzzle_rating, result, user_moves, served_at, answered_at, ms
    )
    SELECT v_id, a.idx, a.puzzle_id, a.puzzle_rating, a.result, coalesce(a.user_moves, ''),
           a.served_at, a.answered_at, a.ms
    FROM jsonb_to_recordset(coalesce(payload->'attempts', '[]'::jsonb)) AS a(
      idx INT, puzzle_id TEXT, puzzle_rating INT, result TEXT, user_moves TEXT,
      served_at TIMESTAMPTZ, answered_at TIMESTAMPTZ, ms INT
    );

    IF v_row.score > 0 THEN
      INSERT INTO puzzle_rush_bests AS b (user_id, mode, best_score, best_run_id, display_name, achieved_at)
      VALUES (v_user, v_row.mode, v_row.score, v_id, v_row.display_name, v_row.ended_at)
      ON CONFLICT (user_id, mode) DO UPDATE
        SET best_score   = EXCLUDED.best_score,
            best_run_id  = EXCLUDED.best_run_id,
            display_name = EXCLUDED.display_name,
            achieved_at  = EXCLUDED.achieved_at
        WHERE EXCLUDED.best_score > b.best_score;
      IF FOUND THEN
        UPDATE puzzle_rush_runs SET is_new_pb = true WHERE id = v_id RETURNING * INTO v_row;
      END IF;
    END IF;
  END IF;

  RETURN jsonb_build_object(
    'status', v_status,
    'run', jsonb_build_object(
      'score', v_row.score,
      'is_new_pb', v_row.is_new_pb,
      'longest_streak', v_row.longest_streak,
      'highest_solved_rating', v_row.highest_solved_rating,
      'avg_ms_per_puzzle', v_row.avg_ms_per_puzzle,
      'duration_ms', v_row.duration_ms
    ),
    'personal_rank', 1 + (
      SELECT count(*) FROM puzzle_rush_runs
      WHERE user_id = v_user AND mode = v_row.mode AND ended_at IS NOT NULL AND score > v_row.score
    ),
    'global_rank', jsonb_build_object(
      'daily', 1 + (
        SELECT count(DISTINCT user_id) FROM puzzle_rush_runs
        WHERE mode = v_row.mode AND user_id IS NOT NULL AND score > v_row.score
          AND ended_at >= (payload->'periods'->>'daily')::timestamptz
      ),
      'weekly', 1 + (
        SELECT count(DISTINCT user_id) FROM puzzle_rush_runs
        WHERE mode = v_row.mode AND user_id IS NOT NULL AND score > v_row.score
          AND ended_at >= (payload->'periods'->>'weekly')::timestamptz
      ),
      'all', 1 + (
        SELECT count(*) FROM puzzle_rush_bests
        WHERE mode = v_row.mode AND best_score > v_row.score
      )
    )
  );
END;
$$;

REVOKE ALL ON FUNCTION puzzle_rush_finish_run(JSONB) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION puzzle_rush_finish_run(JSONB) TO service_role;

COMMIT;
