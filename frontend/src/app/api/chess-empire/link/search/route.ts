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
  getStudentBranch,
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
const RESOLUTION_TTL_MS = 60_000;

/**
 * Session-invariant branch resolution, cached per user. Steps 1–3 of a search —
 * the caller's verified membership, their branch id/name, and the branch invite
 * token — do not change while the parent types, yet the old code re-ran all
 * three on EVERY debounced keystroke, including the ~0.85s analytics profile
 * call (now replaced by a ~0.35s branch-only lookup). Caching the whole
 * resolution per user (60s TTL, per-instance, same in-memory pattern as the
 * rate limiter above) turns every keystroke after the first into just the live
 * CE search + already-linked lookup. Staleness ceiling: a branch/token change
 * takes up to 60s to surface — acceptable for this flow.
 */
interface ResolvedBranch {
  organizationId: string;
  branchId: string;
  branchName: string | null;
  branchToken: string | null;
}

const resolutionCache = new Map<string, { value: ResolvedBranch; expiresAt: number }>();

/** Test-only: drop cached resolutions so per-test mocks don't leak across cases. */
export function _resetResolutionCache(): void {
  resolutionCache.clear();
}

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
  user_id: string | null;
}

/** Linkage of an already-linked roster candidate, keyed by external student id. */
interface LinkedInfo {
  /** True when the existing member row is owned by the caller themselves. */
  ownedBySelf: boolean;
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

/**
 * Which of the candidate students already own a member row in this org, and
 * whether that row belongs to the caller. Already-linked students are no longer
 * stripped — they are surfaced with `alreadyLinked`/`ownedBySelf` flags so the
 * UI can offer "Add to my family" (foreign-owned → auto-accept edge) or show
 * "already yours" (owned by caller).
 */
async function fetchLinkedInfo(
  organizationId: string,
  callerUserId: string,
  studentIds: string[],
): Promise<Map<string, LinkedInfo>> {
  if (studentIds.length === 0) return new Map();
  const { data, error } = await supabaseAdmin
    .from('organization_members')
    .select('external_student_id, user_id')
    .eq('organization_id', organizationId)
    .eq('external_source', 'chess_empire')
    .in('link_status', ['verified', 'frozen'])
    .in('external_student_id', studentIds);
  if (error || !data) return new Map();
  const map = new Map<string, LinkedInfo>();
  for (const r of data as LinkedMemberRow[]) {
    if (!r.external_student_id) continue;
    const ownedBySelf = r.user_id === callerUserId;
    // A student owned by the caller wins over a foreign owner for the flag.
    const prev = map.get(r.external_student_id);
    map.set(r.external_student_id, {
      ownedBySelf: ownedBySelf || (prev?.ownedBySelf ?? false),
    });
  }
  return map;
}

/**
 * Resolve — and cache — the caller's own branch, org and invite token from their
 * verified membership. Returns null when the caller has no verified membership
 * (nothing to search). Throws `ChessEmpireAPIError` if the CE branch lookup
 * fails, so the route can surface a 502. On success the result is cached under
 * the user id for `RESOLUTION_TTL_MS`, so subsequent keystrokes skip the whole
 * membership → branch → token chain.
 */
async function resolveForUser(userId: string): Promise<ResolvedBranch | null> {
  const now = Date.now();
  const cached = resolutionCache.get(userId);
  if (cached && cached.expiresAt > now) return cached.value;

  // Branch is bound to the caller's own verified membership — 'self' wins, else
  // the first verified member. No membership → nothing to search.
  const members = await getVerifiedMembersForUser(userId);
  const primary =
    members.find((m) => m.relationship === 'self' && m.studentId) ??
    members.find((m) => m.studentId) ??
    null;
  if (!primary?.studentId || !primary.orgId) return null;

  // One lightweight REST call for branch id + name (no analytics profile).
  const { branch_id: branchId, branch_name: branchName } = await getStudentBranch(
    primary.studentId,
  );

  // Resolve a branch token opportunistically: it is NOT required to search (the
  // caller is authenticated and their branch+org are already known), but it is
  // returned so the client can hand it to `link/link-existing` for the
  // token-based back-compat path when one exists. Skipped when there is no
  // branch to resolve against.
  const branchToken = branchId
    ? (await resolveBranchToken(branchId))?.token ?? null
    : null;

  const value: ResolvedBranch = {
    // Org comes from the caller's OWN verified membership — never a public token.
    organizationId: primary.orgId,
    branchId,
    branchName,
    branchToken,
  };
  resolutionCache.set(userId, { value, expiresAt: now + RESOLUTION_TTL_MS });
  return value;
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

  // Membership → branch → token, cached per user (see resolveForUser). Only the
  // live search + already-linked lookup below run on every keystroke.
  let resolved: ResolvedBranch | null;
  try {
    resolved = await resolveForUser(userId);
  } catch (err) {
    if (err instanceof ChessEmpireAPIError) {
      console.error('[ce-link-search] CE branch error:', err.statusCode, err.body);
      return NextResponse.json({ error: 'upstream_error' }, { status: 502 });
    }
    throw err;
  }
  if (!resolved) {
    return NextResponse.json({ results: [], branchName: null, branchToken: null });
  }

  const { organizationId, branchId, branchName, branchToken } = resolved;
  if (!branchId) {
    return NextResponse.json({ results: [], branchName, branchToken: null });
  }

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
  const linked = await fetchLinkedInfo(organizationId, userId, candidateIds);

  // Attach linkage flags instead of stripping already-linked candidates: a
  // foreign-owned student can be added via an auto-accept edge, and a student the
  // caller already owns is shown as "already yours".
  const withLinkFlags = <T extends { studentId: string }>(base: T) => {
    const info = linked.get(base.studentId);
    return info ? { ...base, alreadyLinked: true as const, ownedBySelf: info.ownedBySelf } : base;
  };

  const studentResults = activeStudents.map((s) =>
    withLinkFlags({
      studentId: s.id,
      firstName: s.first_name,
      lastName: s.last_name || '',
      branchName: branchName ?? '',
      type: 'student' as const,
    }),
  );

  const coachResults = coaches.map((c) =>
    withLinkFlags({
      studentId: c.id,
      firstName: c.first_name,
      lastName: c.last_name || '',
      branchName: branchName ?? '',
      type: 'coach' as const,
    }),
  );

  const results = [...studentResults, ...coachResults].slice(0, MAX_RESULTS);

  return NextResponse.json({ results, branchName, branchToken });
}
