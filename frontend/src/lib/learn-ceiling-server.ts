/**
 * Server-side Learn ceiling resolver for restricted (frozen/expired) members.
 *
 * Fetches the course list (public) plus the signed-in user's per-course progress
 * (authenticated) and derives their current-level ceiling with the pure
 * `resolveRestrictedCeiling`. Powers two server surfaces that must NOT trust
 * client state:
 *   - the `/learn/[courseSlug]` route guard (redirect above-ceiling courses)
 *   - the restricted Home hub ("Level N complete — continue with Level N+1")
 *
 * Best-effort throughout: full-access members short-circuit before any fetch,
 * and any failure resolves to an open state (no ceiling) so a transient backend
 * blip never locks a member out of Learn.
 */
import 'server-only';
import { auth } from '@clerk/nextjs/server';
import { cookies } from 'next/headers';
import { type AccessPolicy } from '@/lib/access-policy';
import { resolveAccessPolicy } from '@/lib/access-membership';
import {
  resolveRestrictedCeiling,
  slugifyTitle,
  type GatingCourse,
} from '@/lib/learn-gating';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:5001';
const DEFAULT_LOCALE = 'ru';
const FETCH_TIMEOUT_MS = 6000;

interface BackendCourse {
  id: string;
  title: string;
  slug?: string | null;
  order_index: number;
}

export interface CeilingCourse {
  id: string;
  slug: string;
  title: string;
  order_index: number;
  progress: number;
  /** 1-based position in the order_index-sorted path. */
  position: number;
}

export interface LearnCeiling {
  policy: AccessPolicy;
  /** 1-based ceiling position, or undefined for full-access / no data. */
  ceiling: number | undefined;
  /** Courses sorted by order_index, enriched with slug + progress + position. */
  courses: CeilingCourse[];
}

/**
 * Resolve the caller's access policy and, when restricted, their Learn ceiling
 * plus the enriched course path. Full-access callers get `ceiling: undefined`
 * and an empty course list with no backend round-trips.
 */
export async function resolveLearnCeiling(): Promise<LearnCeiling> {
  const policy = await resolveAccessPolicy();
  if (policy.mode === 'full') {
    return { policy, ceiling: undefined, courses: [] };
  }

  try {
    const { userId, getToken } = await auth();
    if (!userId) return { policy, ceiling: undefined, courses: [] };

    const cookieStore = await cookies();
    const locale = cookieStore.get('NEXT_LOCALE')?.value || DEFAULT_LOCALE;

    const [rawCourses, progressMap] = await Promise.all([
      fetchCourses(locale),
      fetchProgress(getToken),
    ]);
    if (rawCourses.length === 0) {
      return { policy, ceiling: undefined, courses: [] };
    }

    const sorted = [...rawCourses].sort(
      (a, b) => a.order_index - b.order_index,
    );
    const gating: GatingCourse[] = sorted.map((c) => ({
      id: c.id,
      order_index: c.order_index,
    }));
    const ceiling = resolveRestrictedCeiling(policy, gating, progressMap);

    const courses: CeilingCourse[] = sorted.map((c, i) => ({
      id: c.id,
      slug: c.slug || slugifyTitle(c.title),
      title: c.title,
      order_index: c.order_index,
      progress: progressMap[c.id]?.progress ?? 0,
      position: i + 1,
    }));

    return { policy, ceiling, courses };
  } catch (err) {
    console.error('[learn-ceiling] resolve failed', err);
    return { policy, ceiling: undefined, courses: [] };
  }
}

async function fetchCourses(locale: string): Promise<BackendCourse[]> {
  const res = await fetch(`${BACKEND_URL}/api/courses?locale=${locale}`, {
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data) ? (data as BackendCourse[]) : [];
}

async function fetchProgress(
  getToken: () => Promise<string | null>,
): Promise<Record<string, { progress: number }>> {
  const token = await getToken();
  if (!token) return {};
  const res = await fetch(`${BACKEND_URL}/api/courses/progress`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
  });
  if (!res.ok) return {};
  const data = await res.json();
  return data && typeof data === 'object'
    ? (data as Record<string, { progress: number }>)
    : {};
}
