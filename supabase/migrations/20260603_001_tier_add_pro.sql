-- Migration: Add 'pro' tier to organization_billing.plan check constraint
-- Phase 1 — Self-Serve School Onboarding (PRD §6.0)
--
-- The current `organization_billing.plan` column is a TEXT with CHECK constraint
-- (not an ENUM TYPE as some docs suggest). We widen the allowed values from
-- {starter,growth,enterprise} to {starter,growth,pro,enterprise}.
--
-- This is additive — existing rows still validate. No backfill required.

ALTER TABLE organization_billing
  DROP CONSTRAINT IF EXISTS organization_billing_plan_check;

ALTER TABLE organization_billing
  ADD CONSTRAINT organization_billing_plan_check
  CHECK (plan IN ('starter', 'growth', 'pro', 'enterprise'));
