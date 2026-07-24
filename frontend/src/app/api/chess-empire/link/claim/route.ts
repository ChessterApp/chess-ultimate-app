/**
 * POST /api/chess-empire/link/claim
 *
 * Client-side invite-claim fallback. When Clerk drops `unsafeMetadata` during
 * an OAuth (Google/Apple) sign-up redirect, the webhook never sees the invite
 * JWT and falls back to unreliable email matching. The `no_link` polling
 * component replays the JWT it stashed in browser storage here, running the
 * SAME verification + upsert as the webhook (`linkMemberViaInviteJwt`).
 *
 * Idempotent with the webhook: the member upsert and the single-use
 * consumption both tolerate a concurrent write, so whichever path wins first
 * the other becomes a no-op.
 *
 * Rate-limited per IP consistent with the other invite endpoints
 * (`students/verify`). A `terminal: true` response tells the client to clear
 * the stored JWT (expired / replayed / invalid — it will never succeed).
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth, clerkClient } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { linkMemberViaInviteJwt } from '@/lib/chess-empire-jwt-link';
import { INVITE_JWT_CLAIM_GRACE_SECONDS } from '@/lib/invite-jwt';
import { claimPendingByJwt, CE_PENDING_COOKIE } from '@/lib/pending-registration';

const PER_IP_LIMIT = 10;
const PER_USER_LIMIT = 5;
const RATE_WINDOW_MS = 60 * 60 * 1000;

interface ClaimBody {
  inviteJwt?: string;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

async function getPrimaryEmail(userId: string): Promise<string | null> {
  try {
    const client = await clerkClient();
    const user = await client.users.getUser(userId);
    const primaryId = user.primaryEmailAddressId;
    const hit = user.emailAddresses.find((e) => e.id === primaryId);
    return hit?.emailAddress ?? user.emailAddresses[0]?.emailAddress ?? null;
  } catch {
    return null;
  }
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const ip = clientIp(req);
  const ipLimit = rateLimit(`ce-claim-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(ipLimit.retryAfterSeconds) } },
    );
  }
  const userLimit = rateLimit(`ce-claim-user:${userId}`, PER_USER_LIMIT, RATE_WINDOW_MS);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(userLimit.retryAfterSeconds) } },
    );
  }

  let body: ClaimBody;
  try {
    body = (await req.json()) as ClaimBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }
  const inviteJwt = body.inviteJwt?.trim() ?? '';
  // `req.cookies` is only present on a NextRequest; guard for plain Request.
  const cookieJwt = req.cookies?.get?.(CE_PENDING_COOKIE)?.value?.trim() ?? '';
  if (!inviteJwt && !cookieJwt) {
    return NextResponse.json({ error: 'missing_jwt' }, { status: 400 });
  }

  const email = await getPrimaryEmail(userId);

  const success = (studentId: string) =>
    NextResponse.json({ ok: true, state: 'verified', studentId });

  // (a) Body invite JWT — the client-stashed replay. The 24h grace window lets
  // an expired-but-signed JWT through (jti single-use is still enforced).
  let bodyResult:
    | Awaited<ReturnType<typeof linkMemberViaInviteJwt>>
    | null = null;
  if (inviteJwt) {
    bodyResult = await linkMemberViaInviteJwt(inviteJwt, userId, email, {
      graceSeconds: INVITE_JWT_CLAIM_GRACE_SECONDS,
    });
    if (bodyResult.ok) return success(bodyResult.studentId);
  }

  // (b) ce_pending_jti cookie → server-side pending row. Survives a JWT that
  // expired beyond grace or a browser context that never stashed the JWT.
  if (cookieJwt) {
    const pending = await claimPendingByJwt(cookieJwt, userId, email);
    if (pending.ok) return success(pending.studentId);
    if (pending.reason === 'claimed_by_other') {
      return NextResponse.json(
        { error: 'claimed_by_other', terminal: true },
        { status: 409 },
      );
    }
  }

  // Nothing linked — report the body JWT's diagnosis so the client knows
  // whether to keep replaying. Only `invalid` is signature-class terminal.
  if (bodyResult) {
    switch (bodyResult.reason) {
      case 'jwt_expired':
        return NextResponse.json({ error: 'expired', terminal: true }, { status: 410 });
      case 'jwt_replayed':
        // Already consumed — the webhook or an earlier claim linked this user.
        // Terminal so the client stops replaying; polling will see the row.
        return NextResponse.json({ error: 'replayed', terminal: true }, { status: 409 });
      case 'jwt_invalid':
        return NextResponse.json({ error: 'invalid', terminal: true }, { status: 400 });
      default:
        return NextResponse.json({ error: 'server_error' }, { status: 500 });
    }
  }

  // Cookie-only claim that found no usable pending row.
  return NextResponse.json({ error: 'no_pending', terminal: false }, { status: 404 });
}
