import { Webhook } from 'svix';
import { headers } from 'next/headers';
import { NextResponse } from 'next/server';
import { clerkClient } from '@clerk/nextjs/server';
import { createSubscriber, blocklistSubscriber, LISTS } from '@/lib/listmonk';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { verifyInviteJwt, jwtJtiHash, InviteJwtError } from '@/lib/invite-jwt';

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

async function completeChessEmpireOnboarding(data: ClerkUserData): Promise<void> {
  const clerkUserId = data.id;
  if (!clerkUserId) {
    console.warn('[clerk-webhook] user.created without user id, skipping CE');
    return;
  }

  const unsafe = data.unsafe_metadata || {};
  const rawJwt = unsafe['inviteJwt'];
  if (!rawJwt || typeof rawJwt !== 'string') {
    console.info(
      `[clerk-webhook] user.created for ${clerkUserId} without inviteJwt metadata, skipping (non-CE signup)`,
    );
    return;
  }

  let claims;
  try {
    claims = verifyInviteJwt(rawJwt);
  } catch (err) {
    if (err instanceof InviteJwtError) {
      console.warn(
        `[clerk-webhook] user.created for ${clerkUserId} with invalid invite JWT: ${err.message}`,
      );
      return;
    }
    throw err;
  }

  const jtiHash = jwtJtiHash(rawJwt);

  // 2) Single-use guard — replay is a no-op.
  const existing = await supabaseAdmin
    .from('invite_jwts_consumed')
    .select('jti_hash')
    .eq('jti_hash', jtiHash)
    .limit(1);
  if (existing.data && existing.data.length > 0) {
    console.info(
      `[clerk-webhook] Invite JWT already consumed for user ${clerkUserId}, treating as replay`,
    );
    return;
  }

  // 3) Refuse if the branch invite token has been revoked.
  const tok = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('id, revoked_at')
    .eq('id', claims.branch_token_id)
    .limit(1);
  const tokRow = tok.data?.[0];
  if (!tokRow || tokRow.revoked_at) {
    console.warn(
      `[clerk-webhook] Branch token ${claims.branch_token_id} revoked or missing; refusing to complete user ${clerkUserId}`,
    );
    return;
  }

  // 4) Look up Chesster org row for clerk_org_id.
  const org = await supabaseAdmin
    .from('organizations')
    .select('id, clerk_org_id')
    .eq('id', claims.org_id)
    .limit(1);
  const orgRow = org.data?.[0];
  if (!orgRow) {
    console.error(
      `[clerk-webhook] Invite JWT for user ${clerkUserId} references unknown org ${claims.org_id}`,
    );
    return;
  }

  const nowIso = new Date().toISOString();
  const email = extractPrimaryEmail(data);
  const name = extractName(data);

  // 5) Upsert organization_members with the external linkage. Safe on retry:
  // the (organization_id, external_student_id, external_source) unique
  // constraint turns re-runs into idempotent no-ops.
  const memberPayload: Record<string, unknown> = {
    organization_id: claims.org_id,
    user_id: clerkUserId,
    role: 'student',
    joined_at: nowIso,
    external_student_id: claims.student_id,
    external_source: 'chess_empire',
    link_status: 'verified',
    link_verified_at: nowIso,
  };
  if (email) memberPayload.email = email;
  if (name) memberPayload.name = name;
  await supabaseAdmin
    .from('organization_members')
    .upsert(memberPayload, { onConflict: 'organization_id,external_student_id,external_source' });

  // 6) Add Clerk org membership. 422 = already-member is fine; other errors
  // bubble so Svix retries and the JWT stays unconsumed for the next attempt.
  const clerkOrgId = orgRow.clerk_org_id;
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
          `[clerk-webhook] Clerk reports user ${clerkUserId} is already a member of org ${clerkOrgId}`,
        );
      } else {
        console.error(
          `[clerk-webhook] createOrganizationMembership failed for user ${clerkUserId} org ${clerkOrgId}:`,
          err,
        );
        throw err;
      }
    }
  } else {
    console.warn(
      `[clerk-webhook] Chesster org ${claims.org_id} has no clerk_org_id; skipping Clerk membership call`,
    );
  }

  // 7) Record JWT consumption LAST. If steps 5/6 failed the row is not
  // written and the webhook can safely retry.
  await supabaseAdmin.from('invite_jwts_consumed').insert({
    jti_hash: jtiHash,
    organization_id: claims.org_id,
    branch_token_id: claims.branch_token_id,
    external_student_id: claims.student_id,
    clerk_user_id: clerkUserId,
  });

  console.info(
    `[clerk-webhook] user.created linked user=${clerkUserId} student=${claims.student_id} org=${claims.org_id}`,
  );
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
        // Listmonk sync — Chesster's original behavior. Errors here should not
        // cause Svix retries, so they're swallowed with a log.
        try {
          await syncListmonkUserCreated(data);
        } catch (err) {
          console.error('[clerk-webhook] Listmonk sync failed:', err);
        }
        // Chess Empire onboarding completion — errors here (e.g. Clerk 5xx)
        // bubble so Svix retries and the JWT stays unconsumed.
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
