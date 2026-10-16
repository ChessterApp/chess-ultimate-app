import { Webhook } from 'svix';
import { headers } from 'next/headers';
import { NextResponse } from 'next/server';
import { clerkClient } from '@clerk/nextjs/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { findCoachesByEmail } from '@/lib/chess-empire-client';
import { getMembershipStateForUser } from '@/lib/chess-empire-member';
import { logLinkAttempt, upsertMemberLink, linkMemberViaInviteJwt } from '@/lib/chess-empire-jwt-link';
import { verifyInviteJwt } from '@/lib/invite-jwt';
import { captureServer } from '@/lib/analytics/server';
import { deletePostHogPerson } from '@/lib/analytics/person-delete';
import { ANALYTICS_EVENTS } from '@/lib/analytics/events';
import { scheduleWelcomeDrip } from '@/lib/welcome-drip';

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
  external_accounts?: Array<{ provider?: string }> | null;
  phone_numbers?: unknown[] | null;
  created_at?: number | null;
};

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

/**
 * Display name carried on the invite JWT (online invites only). Online tokens
 * mint the student's typed name as the JWT's `first_name` claim; branch tokens
 * never set it. Legacy online JWTs still in flight are the reason this stays the
 * first-choice source. Any verification failure (expired / bad signature /
 * absent) yields null so the caller falls through to the Clerk field / email.
 */
function extractInviteName(data: ClerkUserData): string | null {
  const rawJwt = (data.unsafe_metadata || {})['inviteJwt'];
  if (typeof rawJwt !== 'string' || !rawJwt) return null;
  try {
    const claims = verifyInviteJwt(rawJwt);
    const first = (claims.first_name || '').trim();
    return first || null;
  } catch {
    return null;
  }
}

/** Sign-up method for analytics — an enum only, never the address itself. */
function signupMethod(data: ClerkUserData): 'google' | 'email' | 'phone' | 'other' {
  const providers = (data.external_accounts || []).map((a) => a?.provider || '');
  if (providers.some((p) => p.includes('google'))) return 'google';
  if (data.email_addresses?.length) return 'email';
  if (data.phone_numbers?.length) return 'phone';
  return 'other';
}

/**
 * Authoritative `user_signed_up` (tracking plan §4 A). The client also fires a
 * once-per-device copy tagged `signup_source: 'client'` (PostHogIdentify) to
 * carry the browser session's UTMs/referrer; funnels count persons, and
 * total-count trends filter on `signup_source = server`.
 */
async function captureUserSignedUp(data: ClerkUserData): Promise<void> {
  if (!data.id) return;
  const createdAt = typeof data.created_at === 'number' ? new Date(data.created_at) : new Date();
  const hasInvite = typeof (data.unsafe_metadata || {})['inviteJwt'] === 'string';
  await captureServer(data.id, ANALYTICS_EVENTS.USER_SIGNED_UP, {
    method: signupMethod(data),
    ...(hasInvite ? { path: 'school' } : {}),
    signup_source: 'server',
    $set_once: { signup_date: createdAt.toISOString().slice(0, 10) },
  });
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

  // The only legitimate email-based match is a coach signing up with their OWN
  // `coaches.email`. Students are never matched by email — a branch-link signup
  // uses any email, so the address carries no signal about which student was
  // picked (that link is handled server-side via pending_registrations / the
  // invite JWT). An exact, case-insensitive `coaches.email` match with a single
  // coach in the org is soft-linked (`pending_confirm`); anything else is
  // `no_match`, which the client-side retry + pending-claim recovery depend on.
  let coaches;
  try {
    coaches = await findCoachesByEmail(orgId, email);
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

  if (coaches.length === 1) {
    const coach = coaches[0];
    try {
      await upsertMemberLink({
        orgId,
        clerkUserId,
        studentId: coach.id,
        linkStatus: 'pending_confirm',
        linkSource: 'email_auto',
        memberType: 'coach',
        // Email is already at hand; name isn't fetched on this path.
        email,
      });
    } catch (err) {
      await logLinkAttempt({
        organization_id: orgId,
        user_id: clerkUserId,
        email,
        attempted_source: 'email_auto',
        status: 'webhook_error',
        candidate_student_ids: [coach.id],
        chosen_student_id: coach.id,
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
      candidate_student_ids: [coach.id],
      chosen_student_id: coach.id,
    });
    console.info(
      `[clerk-webhook] email_auto matched user=${clerkUserId} coach=${coach.id} org=${orgId} (pending_confirm)`,
    );
    return;
  }

  // Zero or multiple coach matches → no_match.
  await logLinkAttempt({
    organization_id: orgId,
    user_id: clerkUserId,
    email,
    attempted_source: 'email_auto',
    status: 'no_match',
    candidate_student_ids: [],
  });
}

async function completeChessEmpireOnboarding(data: ClerkUserData): Promise<void> {
  const clerkUserId = data.id;
  if (!clerkUserId) {
    console.warn('[clerk-webhook] user.created without user id, skipping CE');
    return;
  }
  const email = extractPrimaryEmail(data);

  const rawJwt = (data.unsafe_metadata || {})['inviteJwt'];
  if (!rawJwt || typeof rawJwt !== 'string') {
    await logLinkAttempt({
      organization_id: null,
      user_id: clerkUserId,
      email,
      attempted_source: 'jwt',
      status: 'jwt_missing',
      error_message: 'inviteJwt not present in unsafe_metadata',
    });
    // No JWT on the new user — OAuth often drops unsafeMetadata. Fall through
    // to email auto-match; the client-side claim endpoint is the other backstop.
    await tryEmailAutoMatch(clerkUserId, email);
    return;
  }

  // Reuse the webhook payload's own user fields — no extra Clerk fetch. Prefer
  // the invite JWT's name (online members) → Clerk profile name.
  const name = extractInviteName(data) || extractName(data);
  const result = await linkMemberViaInviteJwt(rawJwt, clerkUserId, email, { name });
  if (result.ok) return;

  // JWT path failed. Replay + hard errors stop here — soft failures (expired /
  // bad signature) fall through to email auto-match so we still catch orphans.
  if (result.fallbackToEmail) {
    await tryEmailAutoMatch(clerkUserId, email);
  }
}

/**
 * Account deletion: remove every row of the user's data in ONE transaction via
 * `public.delete_user_data` (migration 053; per-table decisions in
 * `@/lib/user-data-manifest`). Any failure throws so the webhook returns 500
 * and Svix retries; the RPC is idempotent, so a replay returns zero counts.
 */
async function cascadeDeleteUserData(clerkUserId: string): Promise<void> {
  await removeVoiceNoteAudio(clerkUserId);
  const { data, error } = await supabaseAdmin.rpc('delete_user_data', {
    p_clerk_id: clerkUserId,
  });
  if (error) {
    throw new Error(`delete_user_data failed for user=${clerkUserId}: ${error.message}`);
  }
  console.info(`[clerk-webhook] delete_user_data ok user=${clerkUserId} counts=${JSON.stringify(data)}`);
}

/**
 * Voice-note audio lives in Storage, which the RPC can't reach: remove the
 * user's objects first, while their rows still name them. Best-effort — a
 * storage hiccup (or a database without migration 056) must not block the
 * data deletion itself.
 */
async function removeVoiceNoteAudio(clerkUserId: string): Promise<void> {
  try {
    const { data, error } = await supabaseAdmin
      .from('move_voice_notes')
      .select('storage_path')
      .eq('owner_user_id', clerkUserId);
    if (error) throw error;
    const paths = (data ?? []).map((row: { storage_path: string }) => row.storage_path).filter(Boolean);
    if (paths.length === 0) return;
    const { error: removeError } = await supabaseAdmin.storage.from('move-voice-notes').remove(paths);
    if (removeError) throw removeError;
  } catch (err) {
    console.warn(`[clerk-webhook] voice-note audio cleanup failed user=${clerkUserId}:`, err);
  }
}

type ClerkSessionData = {
  user_id?: string;
};

/**
 * Read a Clerk user's primary email and any invite JWT still sitting in
 * `unsafe_metadata` — session.created events carry only `user_id`, so we have
 * to fetch the full user to recover this context.
 */
async function fetchClerkUserContext(
  clerkUserId: string,
): Promise<{ email: string | null; name: string | null; inviteJwt: string | null }> {
  try {
    const client = await clerkClient();
    const user = await client.users.getUser(clerkUserId);
    const primaryId = user.primaryEmailAddressId;
    const hit = user.emailAddresses.find((e) => e.id === primaryId);
    const email =
      hit?.emailAddress ?? user.emailAddresses[0]?.emailAddress ?? null;
    // Same already-fetched user object — no extra Clerk call.
    const name =
      `${(user.firstName || '').trim()} ${(user.lastName || '').trim()}`.trim() ||
      null;
    const rawJwt = (user.unsafeMetadata || {})['inviteJwt'];
    const inviteJwt = typeof rawJwt === 'string' && rawJwt ? rawJwt : null;
    return { email, name, inviteJwt };
  } catch (err) {
    console.error('[clerk-webhook] fetchClerkUserContext failed:', err);
    return { email: null, name: null, inviteJwt: null };
  }
}

/**
 * `session.created` (sign-in) linking backstop. Pre-existing Chesster accounts
 * never fire `user.created`, so the primary linking path is skipped entirely
 * for them. On sign-in we re-run the same claim: a lingering invite JWT first,
 * then coach-email auto-match. Idempotent — a verified link is
 * terminal, so we no-op rather than downgrade it to pending_confirm.
 */
async function completeChessEmpireSignIn(data: ClerkSessionData): Promise<void> {
  const clerkUserId = data.user_id;
  if (!clerkUserId) {
    console.warn('[clerk-webhook] session.created without user id, skipping CE');
    return;
  }

  // A verified CE link is terminal — never touch it again on later sign-ins.
  let membership;
  try {
    membership = await getMembershipStateForUser(clerkUserId);
  } catch (err) {
    console.error('[clerk-webhook] session.created membership lookup failed:', err);
    return;
  }
  if (membership.state === 'verified') return;

  const { email, name, inviteJwt } = await fetchClerkUserContext(clerkUserId);

  if (inviteJwt) {
    const result = await linkMemberViaInviteJwt(inviteJwt, clerkUserId, email, {
      name,
    });
    // Success or a hard/replay stop → done. Only soft JWT failures fall through
    // to the email auto-match, matching the user.created behavior.
    if (result.ok || !result.fallbackToEmail) return;
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
        await scheduleWelcomeDrip(data);
        await captureUserSignedUp(data);
        await completeChessEmpireOnboarding(data);
        break;
      }

      case 'session.created': {
        await completeChessEmpireSignIn(evt.data as ClerkSessionData);
        break;
      }

      case 'user.deleted': {
        const { id: deletedUserId } = evt.data as { id?: string };

        // DB deletion must succeed — a throw returns 500 so Svix retries. It
        // also removes the welcome drip rows. PostHog below stays best-effort.
        if (deletedUserId) {
          await cascadeDeleteUserData(deletedUserId);
        } else {
          console.warn('[clerk-webhook] user.deleted with no user id, skipping cascade');
        }

        // F11 — drop the PostHog person + events (never throws).
        if (deletedUserId) await deletePostHogPerson(deletedUserId);
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
