/**
 * POST /api/chess-empire/link/link-existing
 *
 * Same-branch instant family link. The parent has picked a student from the
 * roster search (scoped to their own branch via `branchToken`); this endpoint
 * validates the pick server-side and writes the verified `organization_members`
 * row in one call — no invite JWT round-trip, no email, no accept step. It is
 * the consolidation of the older search → verify → claim dance for the in-app
 * "add family member" flow.
 *
 * Consent is implicit here: the target is a roster student inside the parent's
 * own branch (the branch token proves the parent's branch, and we reject any
 * student whose CE branch doesn't match). Cross-branch / online→branch adds go
 * through the email-consent invite flow instead.
 *
 * Rate-limited per IP + per user, consistent with the other invite endpoints.
 */
import 'server-only';
import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { upsertMemberLink } from '@/lib/chess-empire-jwt-link';
import {
  getStudentProfile,
  getStudentDisplayName,
  ChessEmpireAPIError,
} from '@/lib/chess-empire-client';

const PER_IP_LIMIT = 20;
const PER_USER_LIMIT = 10;
const RATE_WINDOW_MS = 60 * 60 * 1000;

interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  expires_at: string | null;
  revoked_at: string | null;
}

interface LinkExistingBody {
  branchToken?: string;
  studentId?: string;
  relationship?: string;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

async function resolveBranchToken(token: string): Promise<BranchTokenRow | null> {
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('id, organization_id, external_branch_id, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as BranchTokenRow;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return row;
}

export async function POST(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const ip = clientIp(req);
  const ipLimit = rateLimit(`ce-link-existing-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(ipLimit.retryAfterSeconds) } },
    );
  }
  const userLimit = rateLimit(`ce-link-existing-user:${userId}`, PER_USER_LIMIT, RATE_WINDOW_MS);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(userLimit.retryAfterSeconds) } },
    );
  }

  let body: LinkExistingBody;
  try {
    body = (await req.json()) as LinkExistingBody;
  } catch {
    return NextResponse.json({ error: 'invalid_body' }, { status: 400 });
  }

  const branchToken = body.branchToken?.trim() ?? '';
  const studentId = body.studentId?.trim() ?? '';
  // Only guardian links come through here; anything else falls back to 'child'.
  const relationship = body.relationship === 'other' ? 'other' : 'child';
  if (!branchToken || !studentId) {
    return NextResponse.json({ error: 'missing_fields' }, { status: 400 });
  }

  const token = await resolveBranchToken(branchToken);
  if (!token) {
    return NextResponse.json({ error: 'invalid_token' }, { status: 401 });
  }

  // One Chesster account per external student (per org, source). If the student
  // is already linked, report it rather than clobbering the existing owner.
  const { data: existing } = await supabaseAdmin
    .from('organization_members')
    .select('id')
    .eq('organization_id', token.organization_id)
    .eq('external_source', 'chess_empire')
    .eq('external_student_id', studentId)
    .in('link_status', ['verified', 'frozen'])
    .maybeSingle();
  if (existing) {
    return NextResponse.json({ error: 'ALREADY_REGISTERED' }, { status: 409 });
  }

  // Confirm the student is real, active, and in the parent's own branch.
  let branchId: string;
  let status: string | null;
  try {
    const profile = await getStudentProfile(studentId);
    branchId = profile.branch_id;
    status = profile.status;
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      const notFound = err.statusCode === 404;
      return NextResponse.json(
        { error: notFound ? 'not_found' : 'upstream_error' },
        { status: notFound ? 404 : 502 },
      );
    }
    throw err;
  }

  if (branchId !== token.external_branch_id) {
    return NextResponse.json({ error: 'branch_mismatch' }, { status: 401 });
  }
  if (status !== 'active') {
    return NextResponse.json({ error: 'inactive' }, { status: 401 });
  }

  const name = await getStudentDisplayName(studentId).catch(() => null);
  try {
    await upsertMemberLink({
      orgId: token.organization_id,
      clerkUserId: userId,
      studentId,
      linkStatus: 'verified',
      linkSource: 'claim',
      relationship,
      externalSource: 'chess_empire',
      name,
    });
  } catch (err) {
    console.error('[chess-empire/link/link-existing] upsert failed', err);
    return NextResponse.json({ error: 'server_error' }, { status: 500 });
  }

  return NextResponse.json({ ok: true, studentId, relationship });
}
