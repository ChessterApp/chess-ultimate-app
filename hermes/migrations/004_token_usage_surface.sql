-- Migration 004: Add surface column to token_usage
-- Records which coach surface a turn came from (text chat / analysis / review)
-- so spend can be broken down per feature. Additive only — never edit 001.

ALTER TABLE token_usage
    ADD COLUMN IF NOT EXISTS surface TEXT NOT NULL DEFAULT 'text';

CREATE INDEX IF NOT EXISTS idx_token_usage_surface ON token_usage(surface);
