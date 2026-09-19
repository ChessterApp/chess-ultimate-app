/**
 * GET /api/chess-empire/link/search
 *
 * Authenticated, branch-scoped member search. The signed-in parent's own
 * branch is derived from their verified Chess Empire membership — NOT from a
 * public `branchToken` query param (that is the pre-signup `students/search`
 * endpoint). This backs the "Добавить члена семьи" sub-view in the profile
 * avatar menu: a parent searches the roster of their OWN branch to link a
 * second child (or a coach) instantly.
 *
 * Mirrors `students/search`'s logic — same-branch active students + coaches,
 * already-linked rows stripped, empty query short-circuits (no full-roster
 * leak) — but the branch is resolved from the caller instead of a token:
 *
 *   1. Require a signed-in Clerk user (401 otherwise).
 *   2. Pick the caller's primary verified member ('self' first) → its CE
 *      student id → branch id + branch name (via the CE profile). Its org id
 *      (from the member row) scopes the already-linked filter.
 *   3. Resolve a branch invite token OPPORTUNISTICALLY — it is not required to
 *      search (the caller is already authenticated and branch-bound), but is
 *      returned so the client can pass it to `link/link-existing` when present.
 *   4. Return same-branch matches only; a caller in branch A can never see
 *      branch B's members because the branch is bound to their own membership.
 *
 * Response: `{ results, branchName, branchToken }`. `branchToken` is null when
 * the branch has no active invite token — search still works (the link is
 * written token-lessly), and the client keeps the email-invite fallback too.
 */
import 'server-only';

import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { rateLimit } from '@/lib/in-memory-rate-limit';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { getVerifiedMembersForUser } from '@/lib/chess-empire-member';
import {
  getStudentProfile,
  searchStudentsByBranch,
  searchCoachesByBranch,
  ChessEmpireAPIError,
  type CEStudent,
  type CECoach,
} from '@/lib/chess-empire-client';

const PER_IP_LIMIT = 60;
const PER_USER_LIMIT = 40;
const RATE_WINDOW_MS = 60_000;
const MAX_RESULTS = 20;

interface BranchTokenRow {
  token: string;
  organization_id: string;
  external_branch_id: string;
  kind: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string | null;
}

interface LinkedMemberRow {
  external_student_id: string | null;
}

function clientIp(req: NextRequest): string {
  const forwarded = req.headers.get('x-forwarded-for');
  if (forwarded) return forwarded.split(',')[0]!.trim();
  return req.headers.get('x-real-ip') ?? 'unknown';
}

/**
 * Newest currently-valid, non-online branch invite token for the given branch.
 * Its org id scopes the already-linked filter and the token is passed to
 * `link/link-existing`. Best-effort: null on any failure.
 */
async function resolveBranchToken(
  branchId: string,
): Promise<BranchTokenRow | null> {
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select(
      'token, organization_id, external_branch_id, kind, expires_at, revoked_at, created_at',
    )
    .eq('external_branch_id', branchId);
  if (error || !data) return null;
  const now = Date.now();
  const active = (data as BranchTokenRow[]).filter((row) => {
    if (row.revoked_at) return false;
    if (row.kind === 'online') return false;
    if (row.expires_at && new Date(row.expires_at).getTime() < now) return false;
    return true;
  });
  active.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
  return active[0] ?? null;
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

export async function GET(req: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const ip = clientIp(req);
  const ipLimit = rateLimit(`ce-link-search-ip:${ip}`, PER_IP_LIMIT, RATE_WINDOW_MS);
  if (!ipLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(ipLimit.retryAfterSeconds) } },
    );
  }
  const userLimit = rateLimit(`ce-link-search-user:${userId}`, PER_USER_LIMIT, RATE_WINDOW_MS);
  if (!userLimit.allowed) {
    return NextResponse.json(
      { error: 'rate_limited' },
      { status: 429, headers: { 'Retry-After': String(userLimit.retryAfterSeconds) } },
    );
  }

  const q = new URL(req.url).searchParams.get('q')?.trim() ?? '';

  // Branch is bound to the caller's own verified membership — 'self' wins, else
  // the first verified member. No membership → nothing to search.
  const members = await getVerifiedMembersForUser(userId);
  const primary =
    members.find((m) => m.relationship === 'self' && m.studentId) ??
    members.find((m) => m.studentId) ??
    null;
  if (!primary?.studentId || !primary.orgId) {
    return NextResponse.json({ results: [], branchName: null, branchToken: null });
  }
  // Org comes from the caller's OWN verified membership — never a public token.
  const organizationId = primary.orgId;

  let branchId: string;
  let branchName: string | null;
  try {
    const profile = await getStudentProfile(primary.studentId);
    branchId = profile.branch_id;
    branchName = profile.branch_name ?? null;
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      console.error('[ce-link-search] CE profile error:', err.statusCode, err.body);
      return NextResponse.json({ error: 'upstream_error' }, { status: 502 });
    }
    throw err;
  }
  if (!branchId) {
    return NextResponse.json({ results: [], branchName, branchToken: null });
  }

  // Resolve a branch token opportunistically: it is NOT required to search
  // (the caller is authenticated and their branch+org are already known), but
  // it is returned so the client can hand it to `link/link-existing` for the
  // token-based back-compat path when one exists.
  const tokenRow = await resolveBranchToken(branchId);
  const branchToken = tokenRow?.token ?? null;

  // Empty query never leaks the full roster.
  if (!q) {
    return NextResponse.json({ results: [], branchName, branchToken });
  }

  let students: CEStudent[];
  let coaches: CECoach[];
  try {
    [students, coaches] = await Promise.all([
      searchStudentsByBranch(branchId, q, MAX_RESULTS),
      searchCoachesByBranch(branchId, q, MAX_RESULTS),
    ]);
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      console.error('[ce-link-search] CE search error:', err.statusCode, err.body);
      return NextResponse.json({ error: 'upstream_error' }, { status: 502 });
    }
    throw err;
  }

  // Active-only is enforced at the CE query layer; defensive re-filter here.
  const activeStudents = students.filter((s) => s.status === 'active');
  const candidateIds = [
    ...activeStudents.map((s) => s.id),
    ...coaches.map((c) => c.id),
  ];
  const linked = await fetchLinkedStudentIds(organizationId, candidateIds);

  const studentResults = activeStudents
    .filter((s) => !linked.has(s.id))
    .map((s) => ({
      studentId: s.id,
      firstName: s.first_name,
      lastName: s.last_name || '',
      branchName: branchName ?? '',
      type: 'student' as const,
    }));

  const coachResults = coaches
    .filter((c) => !linked.has(c.id))
    .map((c) => ({
      studentId: c.id,
      firstName: c.first_name,
      lastName: c.last_name || '',
      branchName: branchName ?? '',
      type: 'coach' as const,
    }));

  const results = [...studentResults, ...coachResults].slice(0, MAX_RESULTS);

  return NextResponse.json({ results, branchName, branchToken });
}
