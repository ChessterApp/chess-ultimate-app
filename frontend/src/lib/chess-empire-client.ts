/**
 * Chess Empire API client (TypeScript, server-side).
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc (plan:
 * /root/.claude/plans/ancient-greeting-thimble.md). Used by the server-side
 * search + verify routes and the branch-invite generator script.
 *
 * Two interfaces are wrapped:
 *  - The CE Supabase Edge Functions (`/functions/v1/analytics-students`,
 *    `/functions/v1/tournaments-api/students/search`) authenticated via the
 *    legacy `x-api-key` header.
 *  - The CE Supabase REST API (`/rest/v1/students|branches`) authenticated
 *    via `Authorization: Bearer <service_role_key>` for branch+name filter
 *    queries the analytics endpoint can't express. Both creds live in
 *    `CHESS_EMPIRE_SERVICE_KEY` — read on each method call so tests can
 *    patch the env without re-importing this module.
 *
 * 10-second timeout, no retries. Throws ChessEmpireAPIError on non-2xx.
 */
import 'server-only';

const CE_DEFAULT_BASE = 'https://papgcizhfkngubwofjuo.supabase.co';

const DEFAULT_TIMEOUT_MS = 10_000;
const DEFAULT_SEARCH_LIMIT = 20;

function ceBaseUrl(): string {
  return process.env.CHESS_EMPIRE_SUPABASE_URL || CE_DEFAULT_BASE;
}

function ceFunctionsBase(): string {
  return `${ceBaseUrl()}/functions/v1`;
}

function ceRestBase(): string {
  return `${ceBaseUrl()}/rest/v1`;
}

export interface CEStudent {
  id: string;
  first_name: string;
  last_name: string;
  branch_id: string;
  status: 'active' | 'frozen' | 'left' | string;
  date_of_birth: string | null;
  coach_id?: string | null;
  photo_url?: string | null;
}

export interface CEBranch {
  id: string;
  name: string;
  address?: string | null;
}

export interface CEStudentProfile extends CEStudent {
  coach_name?: string | null;
  branch_name?: string | null;
  current_level?: number | null;
  current_lesson?: number | null;
  total_lessons?: number | null;
  current_rating?: number | null;
  razryad?: string | null;
  current_league?: string | null;
}

export interface CERatingPoint {
  date: string;
  rating: number;
  source?: string;
}

export interface CEAchievement {
  id: string;
  name: string;
  description?: string | null;
  icon_url?: string | null;
  earned_at: string;
}

export interface CEStudentRank {
  branch_rank: number | null;
  school_rank: number | null;
  branch_size: number | null;
  school_size: number | null;
}

export class ChessEmpireAPIError extends Error {
  public readonly statusCode: number;
  public readonly body: unknown;

  constructor(statusCode: number, body: unknown) {
    super(`Chess Empire API ${statusCode}: ${JSON.stringify(body)}`);
    this.statusCode = statusCode;
    this.body = body;
    this.name = 'ChessEmpireAPIError';
  }
}

function getServiceKey(): string {
  const key = process.env.CHESS_EMPIRE_SERVICE_KEY;
  if (!key) {
    throw new ChessEmpireAPIError(500, 'CHESS_EMPIRE_SERVICE_KEY not configured');
  }
  return key;
}

async function ceFetch(
  url: string,
  init: RequestInit,
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') {
      throw new ChessEmpireAPIError(504, 'Chess Empire API timeout');
    }
    throw new ChessEmpireAPIError(502, (err as Error)?.message ?? String(err));
  } finally {
    clearTimeout(timer);
  }
}

async function expectJson<T>(resp: Response): Promise<T> {
  if (resp.status < 200 || resp.status >= 300) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = await resp.text().catch(() => '');
    }
    throw new ChessEmpireAPIError(resp.status, body);
  }
  return (await resp.json()) as T;
}

/**
 * Search students by branch with a name (first OR last) ILIKE filter.
 *
 * Uses the CE Supabase REST API directly — the analytics endpoints don't
 * expose a branch+name combined filter, and the public
 * `/tournaments-api/students/search` is school-wide (no branch scope).
 * Returns up to `limit` rows, default 20.
 */
export async function searchStudentsByBranch(
  branchId: string,
  query: string,
  limit: number = DEFAULT_SEARCH_LIMIT,
): Promise<CEStudent[]> {
  const key = getServiceKey();
  const safeLimit = Math.min(Math.max(1, limit), 50);
  const params = new URLSearchParams({
    branch_id: `eq.${branchId}`,
    status: 'eq.active',
    select: 'id,first_name,last_name,branch_id,status,date_of_birth,coach_id,photo_url',
    limit: String(safeLimit),
    order: 'first_name.asc',
  });
  const trimmed = query.trim();
  if (trimmed) {
    // PostgREST `or=` with comma-separated predicates. ILIKE wildcards are `*`.
    const escaped = trimmed.replace(/[,()*]/g, ' ').trim();
    if (escaped) {
      params.append(
        'or',
        `(first_name.ilike.*${escaped}*,last_name.ilike.*${escaped}*)`,
      );
    }
  }
  const url = `${ceRestBase()}/students?${params.toString()}`;
  const resp = await ceFetch(url, {
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      Accept: 'application/json',
    },
  });
  return expectJson<CEStudent[]>(resp);
}

/**
 * Fetch a single student's full profile by id. Wraps the analytics endpoint;
 * the DOB and `status` fields are the verify gate's inputs.
 */
export async function getStudentProfile(studentId: string): Promise<CEStudentProfile> {
  const key = getServiceKey();
  const url = `${ceFunctionsBase()}/analytics-students?action=profile&student_id=${encodeURIComponent(studentId)}`;
  const resp = await ceFetch(url, {
    headers: { 'x-api-key': key, Accept: 'application/json' },
  });
  const body = await expectJson<{ profile?: CEStudentProfile } | CEStudentProfile>(resp);
  // Analytics endpoints wrap the payload in `{ profile: {...} }`; fall back to
  // a flat shape so a future API change doesn't silently return `undefined`.
  if (body && typeof body === 'object' && 'profile' in body && body.profile) {
    return body.profile as CEStudentProfile;
  }
  return body as CEStudentProfile;
}

/**
 * List all branches in Chess Empire. Used by the one-shot generator script.
 */
export async function getBranches(): Promise<CEBranch[]> {
  const key = getServiceKey();
  const params = new URLSearchParams({
    select: 'id,name,address',
    order: 'name.asc',
  });
  const url = `${ceRestBase()}/branches?${params.toString()}`;
  const resp = await ceFetch(url, {
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      Accept: 'application/json',
    },
  });
  return expectJson<CEBranch[]>(resp);
}

/**
 * Count active students in a branch. Used by the generator to skip empty
 * branches (e.g. НИШ has 0 active students as of 2026-06-30).
 */
export async function countActiveStudentsInBranch(branchId: string): Promise<number> {
  const key = getServiceKey();
  const params = new URLSearchParams({
    branch_id: `eq.${branchId}`,
    status: 'eq.active',
    select: 'id',
  });
  const url = `${ceRestBase()}/students?${params.toString()}`;
  const resp = await ceFetch(url, {
    headers: {
      apikey: key,
      Authorization: `Bearer ${key}`,
      Accept: 'application/json',
      // Supabase exact count header.
      Prefer: 'count=exact',
      Range: '0-0',
    },
  });
  if (resp.status < 200 || resp.status >= 300) {
    let body: unknown;
    try {
      body = await resp.json();
    } catch {
      body = '';
    }
    throw new ChessEmpireAPIError(resp.status, body);
  }
  const contentRange = resp.headers.get('content-range') || '';
  const match = contentRange.match(/\/(\d+|\*)$/);
  if (match && match[1] !== '*') {
    return Number(match[1]);
  }
  // Fallback: count returned rows. With Range 0-0 + select=id this is at most 1,
  // which is sufficient for the boolean "has any active students" check.
  const body = (await resp.json()) as unknown[];
  return Array.isArray(body) ? body.length : 0;
}

/**
 * Phase 3 — Personalized homepage.
 *
 * Fetch a student's recent rating history (last `days` days) for the sparkline
 * on the Empire homepage. The analytics endpoint returns either a wrapped
 * `{ ratings: [...] }` envelope or a flat array — we tolerate both. A 404 is
 * treated as "no data yet" and returns an empty array so the homepage can show
 * an empty state rather than blowing up.
 */
export async function getStudentRatings(
  studentId: string,
  days: number = 30,
): Promise<CERatingPoint[]> {
  const key = getServiceKey();
  const url = `${ceFunctionsBase()}/analytics-students?action=ratings&student_id=${encodeURIComponent(
    studentId,
  )}&days=${encodeURIComponent(String(days))}`;
  const resp = await ceFetch(url, {
    headers: { 'x-api-key': key, Accept: 'application/json' },
  });
  if (resp.status === 404) return [];
  const body = await expectJson<{ ratings?: CERatingPoint[] } | CERatingPoint[]>(resp);
  if (Array.isArray(body)) return body;
  if (body && typeof body === 'object' && Array.isArray(body.ratings)) {
    return body.ratings;
  }
  return [];
}

/**
 * Phase 3 — Personalized homepage.
 *
 * Fetch the student's earned achievements. Same envelope tolerance + 404
 * fallback as ratings.
 */
export async function getStudentAchievements(
  studentId: string,
): Promise<CEAchievement[]> {
  const key = getServiceKey();
  const url = `${ceFunctionsBase()}/analytics-students?action=achievements&student_id=${encodeURIComponent(
    studentId,
  )}`;
  const resp = await ceFetch(url, {
    headers: { 'x-api-key': key, Accept: 'application/json' },
  });
  if (resp.status === 404) return [];
  const body = await expectJson<{ achievements?: CEAchievement[] } | CEAchievement[]>(resp);
  if (Array.isArray(body)) return body;
  if (body && typeof body === 'object' && Array.isArray(body.achievements)) {
    return body.achievements;
  }
  return [];
}

const EMPTY_RANK: CEStudentRank = {
  branch_rank: null,
  school_rank: null,
  branch_size: null,
  school_size: null,
};

/**
 * Phase 3 — Personalized homepage.
 *
 * Fetch the student's leaderboard position within their branch and school.
 * This is a soft-fallback feature: the endpoint may not yet exist (Alex hasn't
 * confirmed the shape), so 404 / unknown shape / network error returns an
 * all-null record rather than throwing — the homepage gracefully omits the
 * rank chip when data is unavailable.
 */
export async function getStudentRank(studentId: string): Promise<CEStudentRank> {
  const key = getServiceKey();
  const url = `${ceFunctionsBase()}/analytics-students?action=rank&student_id=${encodeURIComponent(
    studentId,
  )}`;
  let resp: Response;
  try {
    resp = await ceFetch(url, {
      headers: { 'x-api-key': key, Accept: 'application/json' },
    });
  } catch {
    return { ...EMPTY_RANK };
  }
  if (resp.status === 404) return { ...EMPTY_RANK };
  if (resp.status < 200 || resp.status >= 300) return { ...EMPTY_RANK };
  let body: unknown;
  try {
    body = await resp.json();
  } catch {
    return { ...EMPTY_RANK };
  }
  if (!body || typeof body !== 'object') return { ...EMPTY_RANK };
  const flat = body as Record<string, unknown>;
  const wrapped =
    'rank' in flat && flat.rank && typeof flat.rank === 'object'
      ? (flat.rank as Record<string, unknown>)
      : flat;
  const pick = (k: string): number | null => {
    const v = wrapped[k];
    return typeof v === 'number' && Number.isFinite(v) ? v : null;
  };
  const result: CEStudentRank = {
    branch_rank: pick('branch_rank'),
    school_rank: pick('school_rank'),
    branch_size: pick('branch_size'),
    school_size: pick('school_size'),
  };
  return result;
}
