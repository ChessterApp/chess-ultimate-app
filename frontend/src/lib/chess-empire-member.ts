/**
 * Chess Empire ↔ Chesster membership lookup.
 *
 * The apex CE homepage and `/dashboard` on the CE subdomain read from here to
 * decide what to render:
 *  - `no_link` → no `organization_members` row → name-less "we're getting your
 *    profile ready" copy.
 *  - `pending_confirm` → email auto-match found a single student; the user
 *    must confirm on the homepage before we treat it as verified.
 *  - `verified` → normal personalized surface.
 *
 * `getLinkedStudentId` is kept as a thin wrapper that returns the verified
 * student id or null, for callers that only care about the terminal state.
 *
 * Reads `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` on each call
 * so tests can patch the env without needing to re-import this module — same
 * pattern as `chess-empire-client.ts`.
 *
 * Wrapped in `react cache()` so concurrent server components inside a single
 * render (homepage tree) dedupe the lookup.
 */
import 'server-only';
import { cache } from 'react';
import { createClient } from '@supabase/supabase-js';

export interface GetLinkedStudentIdArgs {
  orgId: string;
  clerkUserId: string;
}

export type MembershipState =
  | 'no_link'
  | 'pending_confirm'
  | 'verified'
  | 'expired';
export type MemberRole = 'student' | 'coach';
export type MemberSource = 'chess_empire' | 'online';
/**
 * Family link type. 'self' = the account owner is the student; 'child'/'other'
 * = a guardian-managed family member. Unknown DB values coerce to 'other';
 * a missing/null value (pre-migration rows) reads as 'self'.
 */
export type MemberRelationship = 'self' | 'child' | 'other';

export interface MembershipStateResult {
  state: MembershipState;
  studentId: string | null;
  memberId: string | null;
  /** Member role — 'coach' rows must not be fed to the student profile API. */
  role: MemberRole;
  /** Onboarding track — 'online' members have no CE profile to render. */
  source: MemberSource;
  /** Family link type (see MemberRelationship). */
  relationship: MemberRelationship;
  /** Owning Clerk organization id; null when there is no row. */
  orgId: string | null;
}

interface MemberRow {
  id: string;
  external_student_id: string | null;
  link_status: string | null;
  role: string | null;
  external_source: string | null;
  /** Absolute access expiry; NULL means never expires. */
  access_expires_at: string | null;
  /** Family link type; absent on pre-migration rows. */
  relationship: string | null;
  organization_id: string | null;
}

const SELECT_COLUMNS =
  'id, external_student_id, link_status, role, external_source, access_expires_at, relationship, organization_id';

/** Both onboarding tracks funnel through the same member lookup. */
const MEMBER_SOURCES = ['chess_empire', 'online'] as const;

function serviceClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    throw new Error(
      'chess-empire-member: NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
    );
  }
  return createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

/**
 * Coerce a raw `relationship` column value. Missing/null (pre-migration rows)
 * → 'self'; a known value passes through; anything else → 'other' so an
 * unexpected label never masquerades as the account owner.
 */
function coerceRelationship(raw: string | null | undefined): MemberRelationship {
  if (raw === null || raw === undefined) return 'self';
  if (raw === 'self' || raw === 'child' || raw === 'other') return raw;
  return 'other';
}

function rowToState(row: MemberRow | null): MembershipStateResult {
  const noLink: MembershipStateResult = {
    state: 'no_link',
    studentId: null,
    memberId: null,
    role: 'student',
    source: 'chess_empire',
    relationship: 'self',
    orgId: null,
  };
  if (!row || !row.external_student_id) return noLink;

  const orgId = row.organization_id ?? null;

  const role: MemberRole = row.role === 'coach' ? 'coach' : 'student';
  const source: MemberSource =
    row.external_source === 'online' ? 'online' : 'chess_empire';
  const relationship = coerceRelationship(row.relationship);
  if (row.link_status === 'verified') {
    // Time-boxed access (online invites): a verified row whose window has
    // elapsed downgrades to `expired` on every read — no cron, checked live.
    // A null/absent `access_expires_at` means the access never expires.
    const expired = row.access_expires_at
      ? new Date(row.access_expires_at).getTime() < Date.now()
      : false;
    return {
      state: expired ? 'expired' : 'verified',
      studentId: row.external_student_id,
      memberId: row.id,
      role,
      source,
      relationship,
      orgId,
    };
  }
  if (row.link_status === 'pending_confirm') {
    return {
      state: 'pending_confirm',
      studentId: row.external_student_id,
      memberId: row.id,
      role,
      source,
      relationship,
      orgId,
    };
  }
  return noLink;
}

/**
 * Deterministically pick the "primary" membership for the legacy single-row
 * helpers from all of a user's rows (fetch order = id ascending). A verified
 * row wins over pending_confirm; among verified, relationship='self' wins, then
 * the earliest. With no verified/pending rows the earliest row's state stands
 * (e.g. a lone expired row). An empty set → no_link.
 */
function pickPrimaryState(
  states: MembershipStateResult[],
): MembershipStateResult {
  if (states.length === 0) return rowToState(null);
  const verified = states.filter((s) => s.state === 'verified');
  if (verified.length > 0) {
    return verified.find((s) => s.relationship === 'self') ?? verified[0];
  }
  const pending = states.find((s) => s.state === 'pending_confirm');
  if (pending) return pending;
  return states[0];
}

/**
 * Fetch ALL member rows for a user (optionally org-scoped), ordered by `id`
 * ascending for a stable, deterministic result. A family account holds several
 * rows here — one per linked student. (`organization_members` has no
 * `created_at`; `id` gives a stable order without risking a query error on a
 * missing column.)
 */
async function fetchMemberRows(
  clerkUserId: string,
  orgId?: string,
): Promise<MemberRow[]> {
  const supabase = serviceClient();
  let query = supabase
    .from('organization_members')
    .select(SELECT_COLUMNS)
    .eq('user_id', clerkUserId);
  if (orgId) query = query.eq('organization_id', orgId);
  const { data, error } = await query
    .in('external_source', MEMBER_SOURCES)
    .order('id', { ascending: true });
  if (error) {
    throw new Error(`chess-empire-member: ${error.message}`);
  }
  return ((data ?? []) as MemberRow[]) ?? [];
}

async function fetchMembershipState({
  orgId,
  clerkUserId,
}: GetLinkedStudentIdArgs): Promise<MembershipStateResult> {
  if (!orgId || !clerkUserId) return rowToState(null);
  const rows = await fetchMemberRows(clerkUserId, orgId);
  return pickPrimaryState(rows.map(rowToState));
}

/**
 * Membership state resolved by Clerk user id alone (no org context).
 *
 * The `/api/chess-empire/link/status` polling endpoint calls this: Chess
 * Empire is a single tenant today, so a user has at most one `chess_empire`
 * member row and org scoping is unnecessary — matching the email-fallback
 * assumption in the webhook. For a family account with several links this
 * returns the deterministic PRIMARY row (see `pickPrimaryState`); use
 * `getVerifiedMembersForUser` to act on any individual family member.
 */
async function fetchMembershipStateForUser(
  clerkUserId: string,
): Promise<MembershipStateResult> {
  if (!clerkUserId) return rowToState(null);
  const rows = await fetchMemberRows(clerkUserId);
  return pickPrimaryState(rows.map(rowToState));
}

/**
 * Every VERIFIED member the caller owns — the family allowlist. Returns one
 * entry per verified link (expiry checked per row, same rule as the single-row
 * helpers), in stable `id` order. Non-verified rows (pending/expired/frozen)
 * are omitted. Empty array when the user has no verified links.
 *
 * This is the ONLY safe source of student ids the register/cancel route may
 * act on: a `student_id` from a request is honoured only if it appears here.
 */
async function fetchVerifiedMembersForUser(
  clerkUserId: string,
): Promise<MembershipStateResult[]> {
  if (!clerkUserId) return [];
  const rows = await fetchMemberRows(clerkUserId);
  return rows.map(rowToState).filter((s) => s.state === 'verified');
}

async function fetchLinkedStudentId(
  args: GetLinkedStudentIdArgs,
): Promise<string | null> {
  const result = await fetchMembershipState(args);
  return result.state === 'verified' ? result.studentId : null;
}

export const getMembershipState = cache(fetchMembershipState);
export const getMembershipStateForUser = cache(fetchMembershipStateForUser);
export const getVerifiedMembersForUser = cache(fetchVerifiedMembersForUser);
export const getLinkedStudentId = cache(fetchLinkedStudentId);
