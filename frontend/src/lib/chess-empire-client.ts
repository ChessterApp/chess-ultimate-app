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

export interface CECoach {
  id: string;
  full_name: string;
  branch_id?: string | null;
}

export interface CEActiveStudent {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string | null;
  status: string;
  branch_id: string;
  coach_id?: string | null;
  current_razryad?: string | null;
  current_league?: string | null;
}

export interface CEBestBot {
  name: string;
  rating: number;
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
  joined_at?: string | null;
  /** Highest value across the profile's `survival_scores` array, or null. */
  best_survival_score?: number | null;
  /** Highest-rated bot the student has beaten, or null if none recorded. */
  best_defeated_bot?: CEBestBot | null;
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
 * Look up CE `students` rows by `parent_email` (case-insensitive).
 *
 * Used by the Clerk webhook fallback path when `inviteJwt` is missing /
 * expired / invalid — an exact `parent_email` match with a single active
 * student in the org is treated as a soft link (`link_status='pending_confirm'`)
 * and the user has to confirm on the homepage before it's promoted to
 * `verified`. Zero or multiple matches short-circuit to the admin queue.
 *
 * `orgId` is accepted for symmetry with the plan spec but not filtered on —
 * CE data doesn't carry a Chesster org id. The webhook only calls this for
 * Chess Empire signups, so scoping is enforced upstream.
 */
export async function findStudentsByParentEmail(
  _orgId: string,
  email: string,
): Promise<CEStudent[]> {
  const key = getServiceKey();
  const trimmed = (email || '').trim();
  if (!trimmed) return [];
  const params = new URLSearchParams({
    parent_email: `eq.${trimmed}`,
    status: 'eq.active',
    select: 'id,first_name,last_name,branch_id,status,date_of_birth,coach_id,photo_url',
    limit: '10',
  });
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

function toFiniteNumber(v: unknown): number | null {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}

/**
 * Best (max) survival score across the CE profile's `survival_scores` array.
 *
 * Tolerant of shape: entries may be plain numbers/numeric strings or objects
 * carrying the value under `score` / `survival_score` / `value`. Returns null
 * for a missing, non-array, empty, or all-invalid input — no throws.
 */
export function bestSurvivalScore(survivalScores: unknown): number | null {
  if (!Array.isArray(survivalScores)) return null;
  let best: number | null = null;
  for (const entry of survivalScores) {
    let val: number | null = null;
    if (typeof entry === 'number' || typeof entry === 'string') {
      val = toFiniteNumber(entry);
    } else if (entry && typeof entry === 'object') {
      const rec = entry as Record<string, unknown>;
      val = toFiniteNumber(rec.score ?? rec.survival_score ?? rec.value);
    }
    if (val !== null && (best === null || val > best)) best = val;
  }
  return best;
}

/**
 * Highest-rated bot the student has beaten, from the CE profile's
 * `bot_battles` array. Every row in `bot_battles` already represents a
 * defeated bot (the table has no win/loss field), so all entries are
 * considered; among them the one with the greatest `bot_rating` wins
 * (first-seen on a tie). Bot name is read from `bot_name` / `name` and rating
 * from `bot_rating` / `rating`. Returns null when the input is missing, empty,
 * or no entry carries both a name and a finite rating — no throws.
 */
export function bestDefeatedBot(botBattles: unknown): CEBestBot | null {
  if (!Array.isArray(botBattles)) return null;
  let best: CEBestBot | null = null;
  for (const entry of botBattles) {
    if (!entry || typeof entry !== 'object') continue;
    const rec = entry as Record<string, unknown>;
    const rating = toFiniteNumber(rec.bot_rating ?? rec.rating);
    if (rating === null) continue;
    const nameRaw = rec.bot_name ?? rec.name;
    const name = typeof nameRaw === 'string' && nameRaw.trim() ? nameRaw.trim() : null;
    if (!name) continue;
    if (best === null || rating > best.rating) best = { name, rating };
  }
  return best;
}

/**
 * Fetch a single student's full profile by id. Wraps the CE analytics Edge
 * Function which returns `{success, data: {student: {...}, ratings, achievements}}`
 * and requires `Authorization: Bearer <service_role_key>` (the `x-api-key`
 * header is rejected with 401).
 *
 * The nested student has `branches: {name}` and `coaches: {first_name, last_name}`
 * expansions — we flatten those into `branch_name` / `coach_name` so callers see
 * a single flat `CEStudentProfile`.
 */
export async function getStudentProfile(studentId: string): Promise<CEStudentProfile> {
  const key = getServiceKey();
  const url = `${ceFunctionsBase()}/analytics-students?action=profile&student_id=${encodeURIComponent(studentId)}`;
  const resp = await ceFetch(url, {
    headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' },
  });
  const body = await expectJson<{ success?: boolean; data?: Record<string, unknown> } | Record<string, unknown>>(resp);
  // Wrapped shape: `{ data: { student, survival_scores, bot_battles, ... } }`
  // where the arrays are siblings of `student`. Flat/unwrapped fallback: the
  // body itself is the student, so `data` and `student` collapse to the same
  // object and the arrays (if any) are read directly off it.
  const data =
    body && typeof body === 'object' && 'data' in body && body.data && typeof body.data === 'object'
      ? (body.data as Record<string, unknown>)
      : (body as Record<string, unknown>);
  const student =
    'student' in data && data.student && typeof data.student === 'object'
      ? (data.student as Record<string, unknown>)
      : data;
  const branches = student.branches as { name?: string } | undefined;
  const coaches = student.coaches as { first_name?: string; last_name?: string } | undefined;
  const coachName = coaches && (coaches.first_name || coaches.last_name)
    ? `${coaches.first_name ?? ''} ${coaches.last_name ?? ''}`.trim()
    : null;
  return {
    ...(student as unknown as CEStudentProfile),
    branch_name: branches?.name ?? null,
    coach_name: coachName,
    best_survival_score: bestSurvivalScore(data.survival_scores ?? student.survival_scores),
    best_defeated_bot: bestDefeatedBot(data.bot_battles ?? student.bot_battles),
  };
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
    headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' },
  });
  if (resp.status === 404) return [];
  const body = await expectJson<{ success?: boolean; data?: unknown } | unknown[]>(resp);
  const rows: unknown[] = Array.isArray(body)
    ? body
    : body && typeof body === 'object' && 'data' in body && Array.isArray((body as { data: unknown }).data)
      ? ((body as { data: unknown[] }).data)
      : [];
  return rows.map((r) => {
    const row = r as Record<string, unknown>;
    return {
      date: (row.rating_date as string) ?? (row.date as string) ?? '',
      rating: Number(row.rating) || 0,
      source: (row.source as string | undefined) ?? undefined,
    };
  });
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
    headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' },
  });
  if (resp.status === 404) return [];
  const body = await expectJson<{ success?: boolean; data?: unknown } | unknown[]>(resp);
  const rows: unknown[] = Array.isArray(body)
    ? body
    : body && typeof body === 'object' && 'data' in body && Array.isArray((body as { data: unknown }).data)
      ? ((body as { data: unknown[] }).data)
      : [];
  return rows.map((r) => r as CEAchievement);
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
 * Fetch the student's leaderboard position within their branch and school,
 * ranked by learning progress (level → lesson → name) over all active students
 * — matching the original CE leaderboard, not internal rating. Backed by the
 * `progress_ranking` action of the CE analytics edge function. This stays a
 * soft-fallback feature: a 404 / unknown shape / network error returns an
 * all-null record rather than throwing — the homepage gracefully omits the
 * rank chip when data is unavailable.
 */
export async function getStudentRank(studentId: string): Promise<CEStudentRank> {
  const key = getServiceKey();
  const url = `${ceFunctionsBase()}/analytics-students?action=progress_ranking&student_id=${encodeURIComponent(
    studentId,
  )}`;
  let resp: Response;
  try {
    resp = await ceFetch(url, {
      headers: { Authorization: `Bearer ${key}`, Accept: 'application/json' },
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
    'data' in flat && flat.data && typeof flat.data === 'object'
      ? (flat.data as Record<string, unknown>)
      : 'rank' in flat && flat.rank && typeof flat.rank === 'object'
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

/**
 * Phase 4 — admin panel roster helpers.
 *
 * The three helpers below back the Chess Empire admin tab on
 * `/admin/students`. They all degrade gracefully: a 404 or any unexpected
 * shape returns `[]` and logs a single warning, so the admin page still
 * renders if a CE endpoint is temporarily down or its contract drifts.
 */
let warnedListBranches = false;
let warnedListCoaches = false;
let warnedListActiveStudents = false;

function isCEBranchArray(x: unknown): x is CEBranch[] {
  return (
    Array.isArray(x) &&
    x.every(
      (r) =>
        r &&
        typeof r === 'object' &&
        typeof (r as { id?: unknown }).id === 'string' &&
        typeof (r as { name?: unknown }).name === 'string',
    )
  );
}

function isCECoachArray(x: unknown): x is CECoach[] {
  return (
    Array.isArray(x) &&
    x.every(
      (r) =>
        r &&
        typeof r === 'object' &&
        typeof (r as { id?: unknown }).id === 'string' &&
        typeof (r as { full_name?: unknown }).full_name === 'string',
    )
  );
}

function isCEActiveStudentArray(x: unknown): x is CEActiveStudent[] {
  return (
    Array.isArray(x) &&
    x.every(
      (r) =>
        r &&
        typeof r === 'object' &&
        typeof (r as { id?: unknown }).id === 'string' &&
        typeof (r as { branch_id?: unknown }).branch_id === 'string',
    )
  );
}

export async function listBranches(): Promise<CEBranch[]> {
  let key: string;
  try {
    key = getServiceKey();
  } catch {
    return [];
  }
  const params = new URLSearchParams({
    select: 'id,name,address',
    order: 'name.asc',
  });
  const url = `${ceRestBase()}/branches?${params.toString()}`;
  let resp: Response;
  try {
    resp = await ceFetch(url, {
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        Accept: 'application/json',
      },
    });
  } catch {
    if (!warnedListBranches) {
      console.warn('[ce-admin] listBranches: network error, returning []');
      warnedListBranches = true;
    }
    return [];
  }
  if (resp.status === 404) return [];
  if (resp.status < 200 || resp.status >= 300) {
    if (!warnedListBranches) {
      console.warn(`[ce-admin] listBranches: HTTP ${resp.status}, returning []`);
      warnedListBranches = true;
    }
    return [];
  }
  let body: unknown;
  try {
    body = await resp.json();
  } catch {
    return [];
  }
  if (isCEBranchArray(body)) return body;
  if (!warnedListBranches) {
    console.warn('[ce-admin] listBranches: unexpected shape, returning []');
    warnedListBranches = true;
  }
  return [];
}

export async function listCoaches(): Promise<CECoach[]> {
  let key: string;
  try {
    key = getServiceKey();
  } catch {
    return [];
  }
  const params = new URLSearchParams({
    select: 'id,full_name,branch_id',
    order: 'full_name.asc',
  });
  const url = `${ceRestBase()}/coaches?${params.toString()}`;
  let resp: Response;
  try {
    resp = await ceFetch(url, {
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        Accept: 'application/json',
      },
    });
  } catch {
    if (!warnedListCoaches) {
      console.warn('[ce-admin] listCoaches: network error, returning []');
      warnedListCoaches = true;
    }
    return [];
  }
  if (resp.status === 404) return [];
  if (resp.status < 200 || resp.status >= 300) {
    if (!warnedListCoaches) {
      console.warn(`[ce-admin] listCoaches: HTTP ${resp.status}, returning []`);
      warnedListCoaches = true;
    }
    return [];
  }
  let body: unknown;
  try {
    body = await resp.json();
  } catch {
    return [];
  }
  if (isCECoachArray(body)) return body;
  if (!warnedListCoaches) {
    console.warn('[ce-admin] listCoaches: unexpected shape, returning []');
    warnedListCoaches = true;
  }
  return [];
}

export async function listActiveStudentsByBranch(
  branchId: string,
): Promise<CEActiveStudent[]> {
  if (!branchId) return [];
  let key: string;
  try {
    key = getServiceKey();
  } catch {
    return [];
  }
  const params = new URLSearchParams({
    branch_id: `eq.${branchId}`,
    status: 'eq.active',
    select:
      'id,first_name,last_name,date_of_birth,status,branch_id,coach_id,current_razryad,current_league',
    order: 'first_name.asc',
  });
  const url = `${ceRestBase()}/students?${params.toString()}`;
  let resp: Response;
  try {
    resp = await ceFetch(url, {
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        Accept: 'application/json',
      },
    });
  } catch {
    if (!warnedListActiveStudents) {
      console.warn(
        '[ce-admin] listActiveStudentsByBranch: network error, returning []',
      );
      warnedListActiveStudents = true;
    }
    return [];
  }
  if (resp.status === 404) return [];
  if (resp.status < 200 || resp.status >= 300) {
    if (!warnedListActiveStudents) {
      console.warn(
        `[ce-admin] listActiveStudentsByBranch: HTTP ${resp.status}, returning []`,
      );
      warnedListActiveStudents = true;
    }
    return [];
  }
  let body: unknown;
  try {
    body = await resp.json();
  } catch {
    return [];
  }
  if (isCEActiveStudentArray(body)) {
    return body.filter((s) => s.status === 'active');
  }
  if (!warnedListActiveStudents) {
    console.warn(
      '[ce-admin] listActiveStudentsByBranch: unexpected shape, returning []',
    );
    warnedListActiveStudents = true;
  }
  return [];
}
