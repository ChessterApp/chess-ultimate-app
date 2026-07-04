import { Webhook } from 'svix';
import { headers } from 'next/headers';
import { NextResponse } from 'next/server';
import { clerkClient } from '@clerk/nextjs/server';
import { createSubscriber, blocklistSubscriber, LISTS } from '@/lib/listmonk';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { verifyInviteJwt, jwtJtiHash, InviteJwtError } from '@/lib/invite-jwt';
import { findStudentsByParentEmail } from '@/lib/chess-empire-client';

type ClerkWebhookEvent = {
  type: string;
  data: Record<string, unknown>;
};

type ClerkEmailAddress = { id: string; email_address: string };

type ClerkUserData = {
  id?: string;
  email_addresses?: ClerkEmailAddress[];
  primary_email_address_id?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  unsafe_metadata?: Record<string, unknown> | null;
};

type AttemptSource = 'jwt' | 'email_auto' | 'admin_manual' | 'backfill';
type AttemptStatus =
  | 'success'
  | 'no_match'
  | 'multiple_match'
  | 'jwt_missing'
  | 'jwt_invalid'
  | 'jwt_expired'
  | 'jwt_replayed'
  | 'webhook_error';

interface AttemptRow {
  organization_id: string | null;
  user_id: string | null;
  email: string | null;
  attempted_source: AttemptSource;
  status: AttemptStatus;
  candidate_student_ids?: string[];
  chosen_student_id?: string | null;
  error_message?: string | null;
}

function extractPrimaryEmail(data: ClerkUserData): string | null {
  const emails = data.email_addresses;
  if (!Array.isArray(emails) || emails.length === 0) return null;
  const primaryId = data.primary_email_address_id;
  if (primaryId) {
    const hit = emails.find((e) => e && e.id === primaryId);
    if (hit && typeof hit.email_address === 'string' && hit.email_address) {
      return hit.email_address;
    }
  }
  const first = emails[0];
  if (first && typeof first.email_address === 'string' && first.email_address) {
    return first.email_address;
  }
  return null;
}

function extractName(data: ClerkUserData): string | null {
  const first = (data.first_name || '').trim();
  const last = (data.last_name || '').trim();
  const full = `${first} ${last}`.trim();
  return full || null;
}

function isAlreadyMemberError(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const e = err as { status?: number; errors?: Array<{ code?: string }> };
  if (e.status === 422) return true;
  if (Array.isArray(e.errors) && e.errors[0]?.code === 'already_a_member_of_organization') {
    return true;
  }
  return false;
}

async function logLinkAttempt(row: AttemptRow): Promise<void> {
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
    console.error('[clerk-webhook] Failed to write link_attempts row:', err);
  }
}

async function syncListmonkUserCreated(data: ClerkUserData): Promise<void> {
  const primaryEmail = extractPrimaryEmail(data);
  if (!primaryEmail) {
    console.warn('[clerk-webhook] user.created with no email, skipping listmonk');
    return;
  }
  const name = extractName(data) || primaryEmail.split('@')[0];
  const result = await createSubscriber(
    primaryEmail,
    name,
    [LISTS.ALL_USERS, LISTS.WELCOME_SEQUENCE],
    { clerk_id: data.id ?? '', source: 'clerk_webhook' },
  );
  console.log(`[clerk-webhook] Subscriber ${primaryEmail}: id=${result.id}, new=${result.created}`);
}

interface JwtLinkContext {
  orgId: string;
  clerkOrgId: string | null;
  studentId: string;
  branchTokenId: string;
  jtiHash: string;
}

/**
 * Try the JWT-based linking path. Returns:
 *   - `{ok:true, ctx}` on happy path (caller must upsert + consume)
 *   - `{ok:false, reason, ctx?}` on any short-circuit — reason is a
 *     link_attempts status. If reason is `jwt_replayed`, the webhook should
 *     stop entirely (no fallback). All other failure reasons should trigger
 *     the email-fallback path.
 */
async function attemptJwtLink(
  data: ClerkUserData,
  clerkUserId: string,
  email: string | null,
): Promise<
  | { ok: true; ctx: JwtLinkContext }
  | { ok: false; reason: AttemptStatus; orgId?: string; stopAfterLog?: boolean }
> {
  const unsafe = data.unsafe_metadata || {};
  const rawJwt = unsafe['inviteJwt'];
  if (!rawJwt || typeof rawJwt !== 'string') {
    await logLinkAttempt({
      organization_id: null,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'jwt_missing',
      error_message: 'inviteJwt not present in unsafe_metadata',
    });
    return { ok: false, reason: 'jwt_missing' };
  }

  let claims;
  try {
    claims = verifyInviteJwt(rawJwt);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    const isExpired = err instanceof InviteJwtError && /expired/i.test(msg);
    const status: AttemptStatus = isExpired ? 'jwt_expired' : 'jwt_invalid';
    await logLinkAttempt({
      organization_id: null,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status,
      error_message: msg,
    });
    return { ok: false, reason: status };
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
    return { ok: false, reason: 'jwt_replayed', orgId: claims.org_id, stopAfterLog: true };
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
    return { ok: false, reason: 'jwt_invalid', orgId: claims.org_id, stopAfterLog: true };
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
    return { ok: false, reason: 'webhook_error', orgId: claims.org_id, stopAfterLog: true };
  }

  return {
    ok: true,
    ctx: {
      orgId: claims.org_id,
      clerkOrgId: (orgRow.clerk_org_id as string | null | undefined) ?? null,
      studentId: claims.student_id,
      branchTokenId: claims.branch_token_id,
      jtiHash,
    },
  };
}

interface UpsertLinkArgs {
  orgId: string;
  clerkUserId: string;
  studentId: string;
  linkStatus: 'verified' | 'pending_confirm';
  linkSource: AttemptSource;
}

async function upsertMemberLink({
  orgId,
  clerkUserId,
  studentId,
  linkStatus,
  linkSource,
}: UpsertLinkArgs): Promise<void> {
  const nowIso = new Date().toISOString();
  const payload: Record<string, unknown> = {
    organization_id: orgId,
    user_id: clerkUserId,
    role: 'student',
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

async function tryEmailAutoMatch(
  clerkUserId: string,
  email: string | null,
): Promise<void> {
  if (!email) {
    await logLinkAttempt({
      organization_id: null,
      user_id: clerkUserId,
      email: null,
      attempted_source: 'email_auto',
      status: 'no_match',
      error_message: 'no primary email on Clerk user',
    });
    return;
  }

  // Look up Chess Empire org(s) this signup could belong to. Today only one
  // org — Chess Empire — is a CE tenant, so we resolve it by slug rather
  // than trying to iterate all orgs. If more schools join CE later, this
  // becomes a per-org loop.
  const orgLookup = await supabaseAdmin
    .from('organizations')
    .select('id')
    .eq('slug', 'chess-empire')
    .limit(1);
  const orgRow = orgLookup.data?.[0];
  if (!orgRow) {
    await logLinkAttempt({
      organization_id: null,
      user_id: clerkUserId,
      email,
      attempted_source: 'email_auto',
      status: 'webhook_error',
      error_message: 'chess-empire org not found in Chesster DB',
    });
    return;
  }
  const orgId = orgRow.id as string;

  let candidates;
  try {
    candidates = await findStudentsByParentEmail(orgId, email);
  } catch (err) {
    await logLinkAttempt({
      organization_id: orgId,
      user_id: clerkUserId,
      email,
      attempted_source: 'email_auto',
      status: 'webhook_error',
      error_message: err instanceof Error ? err.message : String(err),
    });
    return;
  }

  if (candidates.length === 0) {
    await logLinkAttempt({
      organization_id: orgId,
      user_id: clerkUserId,
      email,
      attempted_source: 'email_auto',
      status: 'no_match',
      candidate_student_ids: [],
    });
    return;
  }

  if (candidates.length > 1) {
    await logLinkAttempt({
      organization_id: orgId,
      user_id: clerkUserId,
      email,
      attempted_source: 'email_auto',
      status: 'multiple_match',
      candidate_student_ids: candidates.map((c) => c.id),
    });
    return;
  }

  const chosen = candidates[0];
  try {
    await upsertMemberLink({
      orgId,
      clerkUserId,
      studentId: chosen.id,
      linkStatus: 'pending_confirm',
      linkSource: 'email_auto',
    });
  } catch (err) {
    await logLinkAttempt({
      organization_id: orgId,
      user_id: clerkUserId,
      email,
      attempted_source: 'email_auto',
      status: 'webhook_error',
      candidate_student_ids: [chosen.id],
      chosen_student_id: chosen.id,
      error_message: err instanceof Error ? err.message : String(err),
    });
    return;
  }

  await logLinkAttempt({
    organization_id: orgId,
    user_id: clerkUserId,
    email,
    attempted_source: 'email_auto',
    status: 'success',
    candidate_student_ids: [chosen.id],
    chosen_student_id: chosen.id,
  });
  console.info(
    `[clerk-webhook] email_auto matched user=${clerkUserId} student=${chosen.id} org=${orgId} (pending_confirm)`,
  );
}

async function completeChessEmpireOnboarding(data: ClerkUserData): Promise<void> {
  const clerkUserId = data.id;
  if (!clerkUserId) {
    console.warn('[clerk-webhook] user.created without user id, skipping CE');
    return;
  }
  const email = extractPrimaryEmail(data);

  const jwtResult = await attemptJwtLink(data, clerkUserId, email);

  if (jwtResult.ok) {
    const { ctx } = jwtResult;

    try {
      await upsertMemberLink({
        orgId: ctx.orgId,
        clerkUserId,
        studentId: ctx.studentId,
        linkStatus: 'verified',
        linkSource: 'jwt',
      });
    } catch (err) {
      await logLinkAttempt({
        organization_id: ctx.orgId,
        user_id: clerkUserId,
        email,
        attempted_source: 'jwt',
        status: 'webhook_error',
        chosen_student_id: ctx.studentId,
        error_message: err instanceof Error ? err.message : String(err),
      });
      throw err;
    }

    if (ctx.clerkOrgId) {
      try {
        const client = await clerkClient();
        await client.organizations.createOrganizationMembership({
          organizationId: ctx.clerkOrgId,
          userId: clerkUserId,
          role: 'org:member',
        });
      } catch (err) {
        if (isAlreadyMemberError(err)) {
          console.info(
            `[clerk-webhook] Clerk reports user ${clerkUserId} is already a member of org ${ctx.clerkOrgId}`,
          );
        } else {
          console.error(
            `[clerk-webhook] createOrganizationMembership failed for user ${clerkUserId} org ${ctx.clerkOrgId}:`,
            err,
          );
          throw err;
        }
      }
    } else {
      console.warn(
        `[clerk-webhook] Chesster org ${ctx.orgId} has no clerk_org_id; skipping Clerk membership call`,
      );
    }

    await supabaseAdmin.from('invite_jwts_consumed').insert({
      jti_hash: ctx.jtiHash,
      organization_id: ctx.orgId,
      branch_token_id: ctx.branchTokenId,
      external_student_id: ctx.studentId,
      clerk_user_id: clerkUserId,
    });

    await logLinkAttempt({
      organization_id: ctx.orgId,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'success',
      chosen_student_id: ctx.studentId,
    });

    console.info(
      `[clerk-webhook] user.created linked user=${clerkUserId} student=${ctx.studentId} org=${ctx.orgId}`,
    );
    return;
  }

  // JWT path failed. Replay + hard errors stop here — everything else falls
  // through to email auto-match so we still catch orphans.
  if (jwtResult.stopAfterLog) {
    return;
  }

  await tryEmailAutoMatch(clerkUserId, email);
}

export async function POST(req: Request) {
  const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET;
  if (!WEBHOOK_SECRET) {
    console.error('[clerk-webhook] CLERK_WEBHOOK_SECRET not set');
    return NextResponse.json({ error: 'Server misconfigured' }, { status: 500 });
  }

  const headerPayload = await headers();
  const svix_id = headerPayload.get('svix-id');
  const svix_timestamp = headerPayload.get('svix-timestamp');
  const svix_signature = headerPayload.get('svix-signature');

  if (!svix_id || !svix_timestamp || !svix_signature) {
    return NextResponse.json({ error: 'Missing svix headers' }, { status: 400 });
  }

  const body = await req.text();
  const wh = new Webhook(WEBHOOK_SECRET);

  let evt: ClerkWebhookEvent;
  try {
    evt = wh.verify(body, {
      'svix-id': svix_id,
      'svix-timestamp': svix_timestamp,
      'svix-signature': svix_signature,
    }) as ClerkWebhookEvent;
  } catch (err) {
    console.error('[clerk-webhook] Verification failed:', err);
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
  }

  console.log(`[clerk-webhook] Received event: ${evt.type}`);

  try {
    switch (evt.type) {
      case 'user.created': {
        const data = evt.data as ClerkUserData;
        try {
          await syncListmonkUserCreated(data);
        } catch (err) {
          console.error('[clerk-webhook] Listmonk sync failed:', err);
        }
        await completeChessEmpireOnboarding(data);
        break;
      }

      case 'user.deleted': {
        const { email_addresses } = evt.data as {
          email_addresses?: { email_address: string }[];
        };

        const email = email_addresses?.[0]?.email_address;
        if (email) {
          await blocklistSubscriber(email);
        } else {
          console.warn('[clerk-webhook] user.deleted with no email');
        }
        break;
      }

      default:
        console.log(`[clerk-webhook] Unhandled event type: ${evt.type}`);
    }
  } catch (err) {
    console.error(`[clerk-webhook] Error processing ${evt.type}:`, err);
    return NextResponse.json({ error: 'Processing failed' }, { status: 500 });
  }

  return NextResponse.json({ received: true });
}
