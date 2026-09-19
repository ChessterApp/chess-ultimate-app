/**
 * Cross-branch / online→branch "join family" invites (consent flow).
 *
 * Same-branch family members are linked instantly by a roster pick (a real
 * `organization_members` row owned by the parent — see the `link-existing`
 * route). A family member who lives in a DIFFERENT branch, or an online account
 * inviting a branch player, already owns their own student row, and the
 * `organization_members` unique index `(org, external_student_id, source)`
 * allows exactly one owner per student. So we do NOT duplicate their row.
 *
 * Instead the accepted invite row IS the family edge: it records both parties'
 * real CE student ids, and `getFamilyLinkedStudentIds` reads those edges to
 * widen the tournament-registration allowlist in BOTH directions ("any family
 * member can register any other"). No placeholder-person row is ever minted and
 * no link forms until the target explicitly accepts.
 *
 * All writes go through the service-role client; the route handlers validate the
 * caller's Clerk session first.
 */
import 'server-only';
import { randomUUID } from 'node:crypto';
import { supabaseAdmin } from '@/lib/supabase-admin';

export class InviteNotFoundError extends Error {
  constructor(message = 'invite_not_found') {
    super(message);
    this.name = 'InviteNotFoundError';
  }
}

export class InviteNotPendingError extends Error {
  constructor(message = 'invite_not_pending') {
    super(message);
    this.name = 'InviteNotPendingError';
  }
}

export class InviteEmailMismatchError extends Error {
  constructor(message = 'invite_email_mismatch') {
    super(message);
    this.name = 'InviteEmailMismatchError';
  }
}

/** Invite validity window — a fortnight is plenty for an email round-trip. */
const INVITE_TTL_HOURS = 14 * 24;

type Relationship = 'child' | 'other';

export interface CreateInviteArgs {
  inviterUserId: string;
  inviterOrgId: string | null;
  inviterStudentId: string | null;
  targetName: string | null;
  targetEmail: string | null;
  relationship: Relationship;
}

/** Create a pending invite and return its single-use token. */
export async function createFamilyLinkInvite(
  args: CreateInviteArgs,
): Promise<{ id: string; token: string }> {
  // Two UUIDs, hyphens stripped → 64 hex chars of entropy for the email link.
  const token = `${randomUUID()}${randomUUID()}`.replace(/-/g, '');
  const expiresAt = new Date(
    Date.now() + INVITE_TTL_HOURS * 60 * 60 * 1000,
  ).toISOString();

  const { data, error } = await supabaseAdmin
    .from('family_link_invites')
    .insert({
      token,
      inviter_user_id: args.inviterUserId,
      inviter_org_id: args.inviterOrgId,
      inviter_student_id: args.inviterStudentId,
      target_name: args.targetName,
      target_email: args.targetEmail ? args.targetEmail.trim().toLowerCase() : null,
      relationship: args.relationship,
      status: 'pending',
      expires_at: expiresAt,
    })
    .select('id, token')
    .single();
  if (error || !data) {
    throw new Error(
      `family-link-invite.create: ${error?.message ?? 'no row returned'}`,
    );
  }
  return { id: (data as { id: string }).id, token: (data as { token: string }).token };
}

export interface AutoAcceptEdgeArgs {
  /** The parent gaining register rights (caller). */
  inviterUserId: string;
  inviterOrgId: string | null;
  /** The caller's own CE student id, when they have one (bidirectional edge). */
  inviterStudentId: string | null;
  /** Owner of the target student, stamped as the accepter (may be null). */
  accepterUserId: string | null;
  /** The already-owned student the caller is being granted rights over. */
  targetStudentId: string;
  targetOrgId: string | null;
  targetName: string | null;
  relationship: Relationship;
}

/**
 * Directly create an ALREADY-ACCEPTED family edge — the same-branch "trusted"
 * shortcut for a student who already owns their own account. No email round-trip
 * and no consent step: the caller and the target are provably in the same
 * branch, so the parent gains register rights immediately with NO second member
 * row (the student keeps their own account). Writes one accepted
 * `family_link_invites` row, the same edge `getFamilyLinkedStudentIds` reads.
 * Idempotent: an accepted edge for the same (inviter, target) is reused.
 */
export async function createAutoAcceptedFamilyEdge(
  args: AutoAcceptEdgeArgs,
): Promise<{ id: string; reused: boolean }> {
  // Reuse an existing accepted edge so repeated adds don't pile up rows.
  const { data: existing } = await supabaseAdmin
    .from('family_link_invites')
    .select('id')
    .eq('inviter_user_id', args.inviterUserId)
    .eq('accepted_student_id', args.targetStudentId)
    .eq('status', 'accepted')
    .maybeSingle();
  if (existing) {
    return { id: (existing as { id: string }).id, reused: true };
  }

  const token = `${randomUUID()}${randomUUID()}`.replace(/-/g, '');
  const nowIso = new Date().toISOString();
  const { data, error } = await supabaseAdmin
    .from('family_link_invites')
    .insert({
      token,
      inviter_user_id: args.inviterUserId,
      inviter_org_id: args.inviterOrgId,
      inviter_student_id: args.inviterStudentId,
      target_name: args.targetName,
      target_email: null,
      relationship: args.relationship,
      status: 'accepted',
      accepted_by_user_id: args.accepterUserId,
      accepted_student_id: args.targetStudentId,
      accepted_org_id: args.targetOrgId,
      accepted_at: nowIso,
      // Already accepted, but the column is NOT NULL on some schemas — stamp a
      // far-future window so the row is well-formed.
      expires_at: new Date(
        Date.now() + INVITE_TTL_HOURS * 60 * 60 * 1000,
      ).toISOString(),
    })
    .select('id')
    .single();
  if (error || !data) {
    throw new Error(
      `family-link-invite.autoAccept: ${error?.message ?? 'no row returned'}`,
    );
  }
  return { id: (data as { id: string }).id, reused: false };
}

interface InviteRow {
  id: string;
  inviter_user_id: string;
  target_email: string | null;
  relationship: Relationship;
  status: string;
  expires_at: string;
}

export interface AcceptInviteArgs {
  token: string;
  /** Whoever is accepting — must own the target email when one was specified. */
  accepterUserId: string;
  accepterEmail: string | null;
  /** The accepter's own real CE student id + org (resolved from their self-link). */
  accepterStudentId: string;
  accepterOrgId: string;
}

/**
 * Accept a pending invite → mark it accepted and stamp the accepter's real
 * student id/org onto the row, forming the family edge. Guards: pending only,
 * not expired, and (when the invite named an email) the accepter's email must
 * match. Never mints a placeholder person.
 */
export async function acceptFamilyLinkInvite(
  args: AcceptInviteArgs,
): Promise<{ inviterUserId: string }> {
  const { data, error } = await supabaseAdmin
    .from('family_link_invites')
    .select('id, inviter_user_id, target_email, relationship, status, expires_at')
    .eq('token', args.token)
    .maybeSingle();
  if (error) {
    throw new Error(`family-link-invite.load: ${error.message}`);
  }
  const row = data as InviteRow | null;
  if (!row) throw new InviteNotFoundError();
  if (row.status !== 'pending') throw new InviteNotPendingError();
  if (new Date(row.expires_at).getTime() < Date.now()) {
    await supabaseAdmin
      .from('family_link_invites')
      .update({ status: 'expired' })
      .eq('id', row.id)
      .eq('status', 'pending');
    throw new InviteNotPendingError('invite_expired');
  }
  // Consent guard: an email-targeted invite may only be accepted by that email.
  if (row.target_email) {
    const accepter = (args.accepterEmail ?? '').trim().toLowerCase();
    if (!accepter || accepter !== row.target_email.trim().toLowerCase()) {
      throw new InviteEmailMismatchError();
    }
  }
  const { error: updErr } = await supabaseAdmin
    .from('family_link_invites')
    .update({
      status: 'accepted',
      accepted_by_user_id: args.accepterUserId,
      accepted_student_id: args.accepterStudentId,
      accepted_org_id: args.accepterOrgId,
      accepted_at: new Date().toISOString(),
    })
    .eq('id', row.id)
    .eq('status', 'pending');
  if (updErr) throw new Error(`family-link-invite.accept: ${updErr.message}`);
  return { inviterUserId: row.inviter_user_id };
}

/** Reject a pending invite (declined by the target). Idempotent-ish. */
export async function rejectFamilyLinkInvite(token: string): Promise<void> {
  const { error } = await supabaseAdmin
    .from('family_link_invites')
    .update({ status: 'rejected' })
    .eq('token', token)
    .eq('status', 'pending');
  if (error) throw new Error(`family-link-invite.reject: ${error.message}`);
}

export interface FamilyLinkedStudent {
  studentId: string;
  orgId: string | null;
  relationship: Relationship;
  name: string | null;
}

interface OutgoingRow {
  accepted_student_id: string | null;
  accepted_org_id: string | null;
  relationship: Relationship;
  target_name: string | null;
}
interface IncomingRow {
  inviter_student_id: string | null;
  inviter_org_id: string | null;
}

/**
 * Every student the caller is family-linked to through an ACCEPTED cross-branch
 * invite, in both directions:
 *  - invites the caller SENT → the accepted target's player.
 *  - invites the caller ACCEPTED → the inviter's player.
 *
 * Best-effort: any lookup failure returns [] so the owned-members allowlist is
 * never blocked by this augmentation. De-duplicated by student id.
 */
export async function getFamilyLinkedStudentIds(
  userId: string,
): Promise<FamilyLinkedStudent[]> {
  if (!userId) return [];
  try {
    const [outgoing, incoming] = await Promise.all([
      supabaseAdmin
        .from('family_link_invites')
        .select('accepted_student_id, accepted_org_id, relationship, target_name')
        .eq('inviter_user_id', userId)
        .eq('status', 'accepted'),
      supabaseAdmin
        .from('family_link_invites')
        .select('inviter_student_id, inviter_org_id')
        .eq('accepted_by_user_id', userId)
        .eq('status', 'accepted'),
    ]);

    const out = new Map<string, FamilyLinkedStudent>();
    for (const r of (outgoing.data as OutgoingRow[] | null) ?? []) {
      if (!r.accepted_student_id) continue;
      out.set(r.accepted_student_id, {
        studentId: r.accepted_student_id,
        orgId: r.accepted_org_id,
        relationship: r.relationship === 'other' ? 'other' : 'child',
        name: r.target_name ?? null,
      });
    }
    for (const r of (incoming.data as IncomingRow[] | null) ?? []) {
      if (!r.inviter_student_id || out.has(r.inviter_student_id)) continue;
      out.set(r.inviter_student_id, {
        studentId: r.inviter_student_id,
        orgId: r.inviter_org_id,
        relationship: 'other',
        name: null,
      });
    }
    return [...out.values()];
  } catch (err) {
    console.error('[family-link-invite] getFamilyLinkedStudentIds failed', err);
    return [];
  }
}
