-- Restore lesson completions wiped by the "re-open a finished lesson" bug.
--
-- Re-opening a completed lesson POSTed status 'in_progress', and the progress
-- endpoints overwrote the completed row — but never cleared completed_at. So a
-- row with completed_at set and status <> 'completed' is a lost completion.
--
-- NOT run automatically. Run the dry-run first, then the restore:
--   psql "$SUPABASE_DB_URL" -f backend/scripts/restore_lesson_completions.sql

-- 1. Dry run: how many rows (and users) would be restored.
SELECT count(*) AS rows_to_restore,
       count(DISTINCT user_id) AS users_affected
FROM user_progress
WHERE completed_at IS NOT NULL
  AND status IS DISTINCT FROM 'completed';

-- 2. Restore (uncomment to apply).
-- BEGIN;
-- UPDATE user_progress
-- SET status = 'completed',
--     updated_at = now()
-- WHERE completed_at IS NOT NULL
--   AND status IS DISTINCT FROM 'completed';
-- COMMIT;
