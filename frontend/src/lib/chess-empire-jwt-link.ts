/**
 * Shared Chess Empire invite-JWT linking logic.
 *
 * Extracted from the Clerk `user.created` webhook so the client-side claim
 * endpoint (`/api/chess-empire/link/claim`) can perform the SAME verification
 * and upsert without duplicating it. Both paths:
 *   - verify the HS256 signature + expiry,
 *   - reject replays via `invite_jwts_consumed`,
 *   - validate the branch token + org,
 *   - upsert `organization_members` with `link_status='verified'`,
 *   - grant Clerk org membership,
 *   - record single-use consumption,
 *   - write a `link_attempts` audit row.
 *
 * The two callers race safely: the member upsert is keyed on the unique
 * `(organization_id, external_student_id, external_source)` index and the
 * consumption insert ignores duplicates, so whichever path wins first, the
 * other becomes an idempotent no-op.
 */
import 'server-only';
import { clerkClient } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import {
  verifyInviteJwt,
  jwtJtiHash,
  InviteJwtError,
  type MemberType,
} from '@/lib/invite-jwt';

export type AttemptSource = 'jwt' | 'email_auto' | 'admin_manual' | 'backfill';
export type AttemptStatus =
  | 'success'
  | 'no_match'
  | 'multiple_match'
  | 'jwt_missing'
  | 'jwt_invalid'
  | 'jwt_expired'
  | 'jwt_replayed'
  | 'webhook_error';

export interface AttemptRow {
  organization_id: string | null;
  user_id: string | null;
  email: string | null;
  attempted_source: AttemptSource;
  status: AttemptStatus;
  candidate_student_ids?: string[];
  chosen_student_id?: string | null;
  error_message?: string | null;
}

export async function logLinkAttempt(row: AttemptRow): Promise<void> {
  try {
    await supabaseAdmin.from('link_attempts').insert({
      organization_id: row.organization_id,
      user_id: row.user_id,
      email: row.email,
      attempted_source: row.attempted_source,
      status: row.status,
      candidate_student_ids: row.candidate_student_ids ?? null,
      chosen_student_id: row.chosen_student_id ?? null,
      error_message: row.error_message ?? null,
    });
  } catch (err) {
    console.error('[ce-link] Failed to write link_attempts row:', err);
  }
}

export function isAlreadyMemberError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const e = err as { status?: number; errors?: Array<{ code?: string }> };
  if (e.status === 422) return true;
  if (Array.isArray(e.errors) && e.errors[0]?.code === 'already_a_member_of_organization') {
    return true;
  }
  return false;
}

export interface UpsertLinkArgs {
  orgId: string;
  clerkUserId: string;
  studentId: string;
  linkStatus: 'verified' | 'pending_confirm';
  linkSource: AttemptSource;
  /** Member role written to the row. Defaults to 'student'. */
  memberType?: 'student' | 'coach';
}

export async function upsertMemberLink({
  orgId,
  clerkUserId,
  studentId,
  linkStatus,
  linkSource,
  memberType = 'student',
}: UpsertLinkArgs): Promise<void> {
  const nowIso = new Date().toISOString();
  const payload: Record<string, unknown> = {
    organization_id: orgId,
    user_id: clerkUserId,
    // Coach UUIDs share the external_student_id column, discriminated by role.
    role: memberType === 'coach' ? 'coach' : 'student',
    joined_at: nowIso,
    external_student_id: studentId,
    external_source: 'chess_empire',
    link_status: linkStatus,
    link_source: linkSource,
  };
  if (linkStatus === 'verified') {
    payload.link_verified_at = nowIso;
  }
  const { error } = await supabaseAdmin
    .from('organization_members')
    .upsert(payload, {
      onConflict: 'organization_id,external_student_id,external_source',
    });
  if (error) {
    throw new Error(`organization_members upsert failed: ${error.message}`);
  }
}

export type JwtLinkResult =
  | { ok: true; orgId: string; studentId: string; memberType: MemberType }
  | { ok: false; reason: AttemptStatus; fallbackToEmail: boolean };

/**
 * Verify an invite JWT and, on success, link the Clerk user to their Chess
 * Empire student/coach record. Every short-circuit is audit-logged. Returns a
 * discriminated result — the caller decides HTTP status / email fallback.
 *
 * `fallbackToEmail` is only `true` for soft JWT failures (missing signature
 * secret aside — expired/invalid signature): the webhook then tries parent
 * email auto-match. Replay and hard errors set it `false` (stop).
 */
export async function linkMemberViaInviteJwt(
  rawJwt: string,
  clerkUserId: string,
  email: string | null,
): Promise<JwtLinkResult> {
  let claims;
  try {
    claims = verifyInviteJwt(rawJwt);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    const isExpired = err instanceof InviteJwtError && /expired/i.test(msg);
    const reason: AttemptStatus = isExpired ? 'jwt_expired' : 'jwt_invalid';
    await logLinkAttempt({
      organization_id: null,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: reason,
      error_message: msg,
    });
    return { ok: false, reason, fallbackToEmail: true };
  }

  const jtiHash = jwtJtiHash(rawJwt);

  const existing = await supabaseAdmin
    .from('invite_jwts_consumed')
    .select('jti_hash')
    .eq('jti_hash', jtiHash)
    .limit(1);
  if (existing.data && existing.data.length > 0) {
    await logLinkAttempt({
      organization_id: claims.org_id,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'jwt_replayed',
      chosen_student_id: claims.student_id,
      error_message: 'invite_jwts_consumed already contains this jti_hash',
    });
    return { ok: false, reason: 'jwt_replayed', fallbackToEmail: false };
  }

  const tok = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('id, revoked_at')
    .eq('id', claims.branch_token_id)
    .limit(1);
  const tokRow = tok.data?.[0];
  if (!tokRow || tokRow.revoked_at) {
    await logLinkAttempt({
      organization_id: claims.org_id,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'jwt_invalid',
      error_message: `branch_token ${claims.branch_token_id} revoked or missing`,
    });
    return { ok: false, reason: 'jwt_invalid', fallbackToEmail: false };
  }

  const org = await supabaseAdmin
    .from('organizations')
    .select('id, clerk_org_id')
    .eq('id', claims.org_id)
    .limit(1);
  const orgRow = org.data?.[0];
  if (!orgRow) {
    await logLinkAttempt({
      organization_id: claims.org_id,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'webhook_error',
      error_message: `unknown org ${claims.org_id}`,
    });
    return { ok: false, reason: 'webhook_error', fallbackToEmail: false };
  }

  try {
    await upsertMemberLink({
      orgId: claims.org_id,
      clerkUserId,
      studentId: claims.student_id,
      linkStatus: 'verified',
      linkSource: 'jwt',
      memberType: claims.member_type,
    });
  } catch (err) {
    await logLinkAttempt({
      organization_id: claims.org_id,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'webhook_error',
      chosen_student_id: claims.student_id,
      error_message: err instanceof Error ? err.message : String(err),
    });
    return { ok: false, reason: 'webhook_error', fallbackToEmail: false };
  }

  const clerkOrgId = (orgRow.clerk_org_id as string | null | undefined) ?? null;
  if (clerkOrgId) {
    try {
      const client = await clerkClient();
      await client.organizations.createOrganizationMembership({
        organizationId: clerkOrgId,
        userId: clerkUserId,
        role: 'org:member',
      });
    } catch (err) {
      if (isAlreadyMemberError(err)) {
        console.info(
          `[ce-link] Clerk reports user ${clerkUserId} is already a member of org ${clerkOrgId}`,
        );
      } else {
        // The Supabase link is already written — a failed Clerk membership call
        // is logged but non-fatal so the personalized dashboard still renders.
        console.error(
          `[ce-link] createOrganizationMembership failed for user ${clerkUserId} org ${clerkOrgId}:`,
          err,
        );
      }
    }
  } else {
    console.warn(
      `[ce-link] Chesster org ${claims.org_id} has no clerk_org_id; skipping Clerk membership call`,
    );
  }

  // Single-use consumption. `ignoreDuplicates` keeps the webhook + claim race
  // idempotent: the loser silently no-ops on the jti_hash PK conflict.
  await supabaseAdmin.from('invite_jwts_consumed').upsert(
    {
      jti_hash: jtiHash,
      organization_id: claims.org_id,
      branch_token_id: claims.branch_token_id,
      external_student_id: claims.student_id,
      clerk_user_id: clerkUserId,
    },
    { onConflict: 'jti_hash', ignoreDuplicates: true },
  );

  await logLinkAttempt({
    organization_id: claims.org_id,
    user_id: clerkUserId,
    email,
    attempted_source: 'jwt',
    status: 'success',
    chosen_student_id: claims.student_id,
  });

  console.info(
    `[ce-link] linked user=${clerkUserId} student=${claims.student_id} org=${claims.org_id}`,
  );

  return {
    ok: true,
    orgId: claims.org_id,
    studentId: claims.student_id,
    memberType: claims.member_type,
  };
}
