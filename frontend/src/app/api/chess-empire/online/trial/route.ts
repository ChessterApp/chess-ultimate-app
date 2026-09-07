/**
 * Online-students 3-day trial → invite JWT.
 *
 * POST with `{ branchToken }` (optional `name`). Online invite tokens
 * (`branch_invite_tokens.kind='online'`) have no Chess Empire roster to match
 * against, so — unlike the branch `students/verify` route — we skip the search /
 * confirm / DOB gate entirely. We mint a short-lived HS256 invite JWT carrying a
 * generated synthetic student id, `member_type='student'`,
 * `external_source='online'`, and a HARDCODED 72-hour access TTL. The webhook /
 * claim path then writes a time-boxed `organization_members` row
 * (`access_expires_at = now() + access_ttl_hours`).
 *
 * ⚠️ TTL trap: the token's `access_ttl_hours` is NULL on purpose (so roster
 * students are permanent). The trial MUST NOT read it — a NULL would mint a
 * never-expiring member. TTL is therefore hardcoded here.
 *
 * `name` is optional: the Clerk sign-up form asks for it again, so the welcome
 * interstitial no longer collects one. When present it rides along as the JWT's
 * `first_name` claim (the webhook's preferred display-name source); when absent
 * the claim is simply omitted — we never invent a placeholder.
 *
 * Rate-limited per IP consistent with the other invite endpoints.
 */
import 'server-only';

import { NextRequest, NextResponse } from 'next/server';
import { randomUUID } from 'node:crypto';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { signInviteJwt } from '@/lib/invite-jwt';

const PER_IP_LIMIT = 20;
const RATE_WINDOW_MS = 60 * 60 * 1000;
// Hardcoded — never read from the token row (it is NULL on purpose; see above).
const TRIAL_TTL_HOURS = 72;

interface OnlineTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  kind: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

interface TrialBody {
  branchToken?: string;
  name?: string;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

async function resolveOnlineToken(token: string): Promise<OnlineTokenRow | null> {
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('id, organization_id, external_branch_id, kind, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as OnlineTokenRow;
  if (row.kind !== 'online') return null;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return row;
}

export async function POST(req: NextRequest) {
  const ip = clientIp(req);
  const limit = rateLimit(`ce-online-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } },
    );
  }

  let body: TrialBody;
  try {
    body = (await req.json()) as TrialBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const branchToken = body.branchToken?.trim() ?? '';
  const name = body.name?.trim() ?? '';
  if (!branchToken) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }

  const token = await resolveOnlineToken(branchToken);
  if (!token) {
    return NextResponse.json({ error: 'invalid_token' }, { status: 401 });
  }

  // No CE record to point at — each online sign-up gets its own synthetic
  // student id so the unique (org, external_student_id, source) key holds.
  const syntheticStudentId = randomUUID();

  const inviteJwt = signInviteJwt({
    student_id: syntheticStudentId,
    branch_id: token.external_branch_id,
    branch_token_id: token.id,
    org_id: token.organization_id,
    // member_type omitted → verify normalizes to 'student'.
    external_source: 'online',
    // Hardcoded trial window — deliberately not sourced from the token.
    access_ttl_hours: TRIAL_TTL_HOURS,
    // Only carry a name when one was actually provided — no placeholder.
    ...(name ? { first_name: name } : {}),
  });

  return NextResponse.json({ inviteJwt });
}
