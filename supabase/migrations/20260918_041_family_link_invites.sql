-- Migration: cross-branch / online→branch "join family" invites.
--
-- Family Registration (universal add). Same-branch family members are linked
-- instantly via a roster pick (no row here). A family member who lives in a
-- DIFFERENT branch — or an online account inviting a branch student — cannot be
-- auto-linked without consent, so the inviter creates a pending invite here and
-- the target receives a "join family" email. The reciprocal
-- `organization_members` link forms ONLY when the target accepts.
--
-- No placeholder-person rows are ever minted: on accept we reuse the target's
-- own real student id.
--
-- Idempotent. Safe to re-run. NOT applied to any database by this change.

CREATE TABLE IF NOT EXISTS family_link_invites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Unguessable, single-use accept token delivered in the email link.
  token text NOT NULL UNIQUE,
  -- Clerk user id of the family member who sent the invite.
  inviter_user_id text NOT NULL,
  -- Org the inviter belongs to (Chess Empire tenant). May be null if unresolved.
  inviter_org_id uuid,
  -- The inviter's own CE student id, captured at send time so the accepted edge
  -- is bidirectional: the target can register the inviter's player too.
  inviter_student_id uuid,
  -- Optional display name the inviter typed for the target.
  target_name text,
  -- Target's email (the consent channel). Null for a name-only invite.
  target_email text,
  -- Family link type written to the resulting member row.
  relationship text NOT NULL DEFAULT 'child'
    CHECK (relationship IN ('child', 'other')),
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'accepted', 'rejected', 'expired')),
  -- Clerk user id of whoever accepted (must match target_email when set).
  accepted_by_user_id text,
  -- The accepter's own CE student id + org, captured at accept time — the real
  -- player the inviter may now register (no placeholder person is minted).
  accepted_student_id uuid,
  accepted_org_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz
);

CREATE INDEX IF NOT EXISTS family_link_invites_inviter_idx
  ON family_link_invites (inviter_user_id);

CREATE INDEX IF NOT EXISTS family_link_invites_target_email_idx
  ON family_link_invites (lower(target_email));

COMMENT ON TABLE family_link_invites IS
  'Pending cross-branch / online→branch "join family" invites. The reciprocal organization_members link forms only when the target accepts.';

-- Rollback:
-- DROP TABLE IF EXISTS family_link_invites;
