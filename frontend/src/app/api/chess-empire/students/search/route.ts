/**
 * Public branch-scoped student autocomplete (pre-signup).
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc. A parent on the
 * `/welcome/<branchToken>` page types a name; this endpoint:
 *
 *   1. Resolves the `branchToken` against `branch_invite_tokens` — must
 *      exist, `revoked_at` null, `expires_at` null or in the future.
 *   2. Queries CE Supabase for `status='active'` students in that branch
 *      whose first OR last name matches the query (ILIKE).
 *   3. Excludes students already linked in `organization_members` with
 *      `link_status IN ('verified', 'frozen')` for the resolved org.
 *   4. Returns up to 20 results with last-name initial only — last name
 *      reveals on selection (next step), not on autocomplete.
 *
 * No auth required: this is the pre-signup public endpoint. Rate limit:
 * 30 req/min per IP. Empty query → empty result (no full-roster leak).
 */
import 'server-only';

import { NextRequest, NextResponse } from 'next/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import {
  searchStudentsByBranch,
  ChessEmpireAPIError,
  type CEStudent,
} from '@/lib/chess-empire-client';
import { rateLimit } from '@/lib/in-memory-rate-limit';

const SEARCH_RATE_LIMIT = 30;
const SEARCH_WINDOW_MS = 60_000;
const MAX_RESULTS = 20;

interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  expires_at: string | null;
  revoked_at: string | null;
}

interface LinkedMemberRow {
  external_student_id: string | null;
}

async function resolveBranchToken(token: string): Promise<BranchTokenRow | null> {
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('id, organization_id, external_branch_id, branch_name, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as BranchTokenRow;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return row;
}

async function fetchLinkedStudentIds(
  organizationId: string,
  studentIds: string[],
): Promise<Set<string>> {
  if (studentIds.length === 0) return new Set();
  const { data, error } = await supabaseAdmin
    .from('organization_members')
    .select('external_student_id')
    .eq('organization_id', organizationId)
    .eq('external_source', 'chess_empire')
    .in('link_status', ['verified', 'frozen'])
    .in('external_student_id', studentIds);
  if (error || !data) return new Set();
  return new Set(
    (data as LinkedMemberRow[])
      .map((r) => r.external_student_id)
      .filter((id): id is string => !!id),
  );
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

export async function GET(req: NextRequest) {
  const ip = clientIp(req);
  const limit = rateLimit(`ce-search:${ip}`, SEARCH_RATE_LIMIT, SEARCH_WINDOW_MS);
  if (!limit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(limit.retryAfterSeconds) } },
    );
  }

  const url = new URL(req.url);
  const branchToken = url.searchParams.get('branchToken')?.trim() ?? '';
  const q = url.searchParams.get('q')?.trim() ?? '';
  if (!branchToken) {
    return NextResponse.json({ error: 'missing_token' }, { status: 400 });
  }

  const token = await resolveBranchToken(branchToken);
  if (!token) {
    return NextResponse.json({ error: 'invalid_token' }, { status: 401 });
  }

  if (!q) {
    return NextResponse.json({ results: [] });
  }

  let students: CEStudent[];
  try {
    students = await searchStudentsByBranch(token.external_branch_id, q, MAX_RESULTS);
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      console.error('[ce-search] CE API error:', err.statusCode, err.body);
      return NextResponse.json({ error: 'upstream_error' }, { status: 502 });
    }
    throw err;
  }

  // Active-only filter is enforced at the CE query layer (status=eq.active).
  // Defensive re-filter here in case the API contract drifts.
  const activeStudents = students.filter((s) => s.status === 'active');
  const studentIds = activeStudents.map((s) => s.id);
  const linked = await fetchLinkedStudentIds(token.organization_id, studentIds);

  const results = activeStudents
    .filter((s) => !linked.has(s.id))
    .slice(0, MAX_RESULTS)
    .map((s) => ({
      studentId: s.id,
      firstName: s.first_name,
      lastNameInitial: (s.last_name || '').charAt(0).toUpperCase(),
      branchName: token.branch_name,
      coachName: null as string | null,
    }));

  return NextResponse.json({ results });
}
