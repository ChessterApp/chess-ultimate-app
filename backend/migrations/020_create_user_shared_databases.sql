-- Shared Databases, Step 1: "Shared with me" subscriptions.
--
-- When a user opens a per-database share link (?sdb=<token>) a subscription row
-- is recorded so the shared database shows up as a persistent, read-only pill
-- across reloads. Deleting a subscription only removes the subscriber's own row
-- — it never touches the owner's database or games. source_token references a
-- user_databases.share_token (string), not a FK, so a revoked token simply stops
-- resolving.
--
-- Idempotent: re-running makes no further changes.
CREATE TABLE IF NOT EXISTS user_shared_databases (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    subscriber_id TEXT NOT NULL,
    source_token TEXT NOT NULL,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (subscriber_id, source_token)
);
CREATE INDEX IF NOT EXISTS idx_user_shared_databases_subscriber
    ON user_shared_databases(subscriber_id);

ALTER TABLE user_shared_databases ENABLE ROW LEVEL SECURITY;
