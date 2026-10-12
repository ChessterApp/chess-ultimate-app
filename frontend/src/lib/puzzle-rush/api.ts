/**
 * Puzzle Rush API client. Not built on `apiFetch`: that helper retries 4xx and
 * drops error bodies; here errors carry the server's `{error}` code and a run
 * is only ever sent by the caller (the outbox owns retries).
 *
 * Auth: signed-in calls send the Clerk bearer token (no cookies), so the same
 * client works from the mobile app with an absolute `base`. `pack` is public.
 *
 * Framework-free (shared with the mobile app): only `fetch`.
 */

import type {
  BestsResponse,
  FinishRequest,
  FinishResponse,
  LeaderboardResponse,
  PackResponse,
  RushMode,
  RushPeriod,
  RushScope,
} from './types';
import { PACK_SIZE } from './pack';

export class RushApiError extends Error {
  status: number;
  code: string;
  body: Record<string, unknown>;
  constructor(status: number, body: Record<string, unknown>) {
    const code = typeof body.error === 'string' ? body.error : `http_${status}`;
    super(code);
    this.name = 'RushApiError';
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

export interface RushAuth {
  /** Clerk `getToken`; resolves null for signed-out users. */
  getToken: () => Promise<string | null>;
}

const NO_AUTH: RushAuth = { getToken: async () => null };

export function localTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Almaty';
  } catch {
    return 'Asia/Almaty';
  }
}

interface RequestInit {
  method?: 'GET' | 'POST';
  body?: unknown;
  query?: Record<string, string>;
  /** Send the local time zone (periods / "today" are the user's local day). */
  tz?: boolean;
}

/** `base`: '/api/puzzlerush' on web; e.g. 'https://chesster.io/api/puzzlerush' on mobile. */
export function createRushApi(base = '/api/puzzlerush') {
  async function request<T>(auth: RushAuth, path: string, init: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {};
    const token = await auth.getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    if (init.body !== undefined) headers['Content-Type'] = 'application/json';

    const params = new URLSearchParams({ ...(init.tz === false ? {} : { tz: localTimeZone() }), ...init.query });
    const res = await fetch(`${base}${path}?${params}`, {
      method: init.method ?? 'GET',
      headers,
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
    });
    const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (!res.ok) throw new RushApiError(res.status, data);
    return data as T;
  }

  return {
    /** Public and cacheable: identical (seed, from, count) always return the same puzzles. */
    pack: (seed: string, from = 0, count = PACK_SIZE) =>
      request<PackResponse>(NO_AUTH, '/pack', { tz: false, query: { seed, from: String(from), count: String(count) } }),
    finish: (auth: RushAuth, body: FinishRequest) =>
      request<FinishResponse>(auth, '/runs/finish', { method: 'POST', body }),
    bests: (auth: RushAuth) => request<BestsResponse>(auth, '/bests'),
    leaderboard: (auth: RushAuth, mode: RushMode, period: RushPeriod, scope: RushScope) =>
      request<LeaderboardResponse>(auth, '/leaderboard', { query: { mode, period, scope } }),
  };
}

export const rushApi = createRushApi();
