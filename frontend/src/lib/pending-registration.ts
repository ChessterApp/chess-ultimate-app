/**
 * Server-side pending branch-link registrations.
 *
 * The durable half of the branch-link durability fix. When the verify route
 * mints an invite JWT (AFTER branch-token validation passed), it also records
 * a `pending_registrations` row keyed by the JWT's sha256 hash and drops an
 * httpOnly `ce_pending_jti` cookie carrying the raw JWT. Completion then no
 * longer depends on Clerk `unsafeMetadata` (dropped by Google OAuth) or on the
 * short JWT TTL — the signed-in user's cookie points back at the pending row.
 *
 * Claiming is single-use: the row is flipped `pending → claimed` with a
 * conditional update that acts as a lock, so a row claimed by one Clerk user
 * can never be re-claimed by a different one.
 */
import 'server-only';
import { cookies } from 'next/headers';
import { clerkClient } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { jwtJtiHash, type MemberType } from '@/lib/invite-jwt';
import {
  upsertMemberLink,
  logLinkAttempt,
  isAlreadyMemberError,
} from '@/lib/chess-empire-jwt-link';

/** httpOnly cookie holding the raw invite JWT, minted at the verify step. */
export const CE_PENDING_COOKIE = 'ce_pending_jti';
/** Rows older than this are treated as expired (checked at read time). */
export const PENDING_REGISTRATION_TTL_MS = 7 * 24 * 60 * 60 * 1000;
/** Cookie lifetime in seconds — matches the row TTL. */
export const PENDING_COOKIE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60;

interface PendingRow {
  id: string;
  student_id: string;
  org_id: string;
  member_type: string | null;
  status: string;
  created_at: string;
  claimed_by_clerk_user_id: string | null;
}

function normalizeMemberType(value: string | null): MemberType {
  return value === 'coach' ? 'coach' : 'student';
}

/**
 * Record a pending registration at mint time. Best-effort: a failure here is
 * non-fatal because the JWT (cookie + `unsafeMetadata`) and the webhook remain
 * backstops. Duplicate mints of the same JWT are idempotent (jti_hash unique).
 */
export async function insertPendingRegistration(args: {
  rawJwt: string;
  studentId: string;
  orgId: string;
  memberType: MemberType;
}): Promise<void> {
  const jtiHash = jwtJtiHash(args.rawJwt);
  const { error } = await supabaseAdmin.from('pending_registrations').upsert(
    {
      jti_hash: jtiHash,
      student_id: args.studentId,
      org_id: args.orgId,
      member_type: args.memberType,
      status: 'pending',
    },
    { onConflict: 'jti_hash', ignoreDuplicates: true },
  );
  if (error) {
    console.error('[ce-pending] failed to insert pending_registration:', error);
  }
}

export type PendingClaimResult =
  | { ok: true; orgId: string; studentId: string; memberType: MemberType }
  | {
      ok: false;
      reason: 'not_found' | 'expired' | 'claimed_by_other' | 'error';
    };

/**
 * Complete a branch link from a pending row identified by a raw invite JWT
 * (from the `ce_pending_jti` cookie). Mirrors `linkMemberViaInviteJwt`'s
 * success path — org member upsert → Clerk org membership → audit — but trusts
 * the server-written pending row instead of re-verifying the JWT, and marks the
 * row claimed for single-use enforcement.
 */
export async function claimPendingByJwt(
  rawJwt: string,
  clerkUserId: string,
  email: string | null,
): Promise<PendingClaimResult> {
  const jtiHash = jwtJtiHash(rawJwt);

  const { data, error } = await supabaseAdmin
    .from('pending_registrations')
    .select(
      'id, student_id, org_id, member_type, status, created_at, claimed_by_clerk_user_id',
    )
    .eq('jti_hash', jtiHash)
    .limit(1)
    .maybeSingle();
  if (error) {
    console.error('[ce-pending] lookup failed:', error);
    return { ok: false, reason: 'error' };
  }
  const row = (data ?? null) as PendingRow | null;
  if (!row) return { ok: false, reason: 'not_found' };

  const memberType = normalizeMemberType(row.member_type);

  // Already claimed: single-use. Same user → idempotent success (the row was
  // linked, polling will see it); different user → hard reject.
  if (row.status === 'claimed') {
    if (row.claimed_by_clerk_user_id === clerkUserId) {
      return { ok: true, orgId: row.org_id, studentId: row.student_id, memberType };
    }
    return { ok: false, reason: 'claimed_by_other' };
  }

  const ageMs = Date.now() - new Date(row.created_at).getTime();
  if (row.status === 'expired' || ageMs > PENDING_REGISTRATION_TTL_MS) {
    await supabaseAdmin
      .from('pending_registrations')
      .update({ status: 'expired' })
      .eq('id', row.id)
      .eq('status', 'pending');
    return { ok: false, reason: 'expired' };
  }

  // Atomically claim the row FIRST — the `status = pending` guard is the lock
  // that makes the link single-use even under a concurrent race.
  const nowIso = new Date().toISOString();
  const { data: won, error: claimErr } = await supabaseAdmin
    .from('pending_registrations')
    .update({
      status: 'claimed',
      claimed_by_clerk_user_id: clerkUserId,
      claimed_at: nowIso,
    })
    .eq('id', row.id)
    .eq('status', 'pending')
    .select('id');
  if (claimErr) {
    console.error('[ce-pending] claim update failed:', claimErr);
    return { ok: false, reason: 'error' };
  }
  if (!won || won.length === 0) {
    // Lost the race — someone flipped the row between our read and update.
    const { data: fresh } = await supabaseAdmin
      .from('pending_registrations')
      .select('claimed_by_clerk_user_id')
      .eq('id', row.id)
      .maybeSingle();
    const winner = (fresh as { claimed_by_clerk_user_id: string | null } | null)
      ?.claimed_by_clerk_user_id;
    if (winner === clerkUserId) {
      return { ok: true, orgId: row.org_id, studentId: row.student_id, memberType };
    }
    return { ok: false, reason: 'claimed_by_other' };
  }

  // We own the row — complete the link exactly like the JWT success path.
  try {
    await upsertMemberLink({
      orgId: row.org_id,
      clerkUserId,
      studentId: row.student_id,
      linkStatus: 'verified',
      linkSource: 'jwt',
      memberType,
    });
  } catch (err) {
    // Roll the lock back so the row can be retried by the webhook / JWT-body
    // path rather than being stuck claimed with no member row.
    await supabaseAdmin
      .from('pending_registrations')
      .update({ status: 'pending', claimed_by_clerk_user_id: null, claimed_at: null })
      .eq('id', row.id);
    await logLinkAttempt({
      organization_id: row.org_id,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'webhook_error',
      chosen_student_id: row.student_id,
      error_message: err instanceof Error ? err.message : String(err),
    });
    return { ok: false, reason: 'error' };
  }

  const org = await supabaseAdmin
    .from('organizations')
    .select('clerk_org_id')
    .eq('id', row.org_id)
    .limit(1);
  const clerkOrgId =
    (org.data?.[0]?.clerk_org_id as string | null | undefined) ?? null;
  if (clerkOrgId) {
    try {
      const client = await clerkClient();
      await client.organizations.createOrganizationMembership({
        organizationId: clerkOrgId,
        userId: clerkUserId,
        role: 'org:member',
      });
    } catch (err) {
      if (!isAlreadyMemberError(err)) {
        // The Supabase link is already written — a failed Clerk membership call
        // is logged but non-fatal so the personalized dashboard still renders.
        console.error(
          `[ce-pending] createOrganizationMembership failed for user ${clerkUserId} org ${clerkOrgId}:`,
          err,
        );
      }
    }
  }

  await logLinkAttempt({
    organization_id: row.org_id,
    user_id: clerkUserId,
    email,
    attempted_source: 'jwt',
    status: 'pending_row_success',
    chosen_student_id: row.student_id,
  });

  console.info(
    `[ce-pending] linked user=${clerkUserId} student=${row.student_id} org=${row.org_id} via pending row`,
  );

  return { ok: true, orgId: row.org_id, studentId: row.student_id, memberType };
}

/**
 * Server-side auto-claim: read the `ce_pending_jti` cookie and, if present,
 * complete the pending link for the signed-in user. Called wherever the no-link
 * state is about to be rendered so a same-browser sign-up never sees the
 * waiting screen. Returns `true` iff a link now exists for this user.
 */
export async function autoClaimPendingCookie(
  clerkUserId: string,
): Promise<boolean> {
  let rawJwt: string | undefined;
  try {
    const store = await cookies();
    rawJwt = store.get(CE_PENDING_COOKIE)?.value;
  } catch {
    return false;
  }
  if (!rawJwt) return false;
  try {
    const result = await claimPendingByJwt(rawJwt, clerkUserId, null);
    return result.ok;
  } catch (err) {
    console.error('[ce-pending] auto-claim failed:', err);
    return false;
  }
}
