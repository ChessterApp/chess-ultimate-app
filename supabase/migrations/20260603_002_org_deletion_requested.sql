-- Migration: Add deletion_requested_at to organizations
-- Phase 1 — Self-Serve School Onboarding (PRD §7 — Delete School)
--
-- Self-serve deletion: when an owner confirms "Delete school" we set this
-- timestamp + email Alex. A separate ops job (out of scope here) hard-deletes
-- ~30 days later. Nullable timestamp + no backfill so we never collide with
-- the existing `status` enum (active | suspended | trial), which is read in
-- many places and would force a cascade of switch updates if extended.

ALTER TABLE organizations
  ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN organizations.deletion_requested_at IS
  'Set when an org owner requests self-serve deletion. NULL = active. '
  'A scheduled hard-delete sweeps rows 30 days after this timestamp.';
