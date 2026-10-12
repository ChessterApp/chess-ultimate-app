/**
 * Puzzle Rush API client. Not built on `apiFetch`: that helper retries 4xx and
 * drops error bodies, but a rush needs the 409 `run_over` body (it carries the
 * results) and must never replay a move.
 *
 * Auth: signed-in calls send the Clerk bearer token; guest calls send the
 * run's `guest_token` as `X-Guest-Token`.
 */

import type {
  BestsResponse,
  CreateRunResponse,
  LeaderboardResponse,
  MoveResponse,
  QuitResponse,
  RunSummary,
  RushMode,
  RushPeriod,
  RushScope,
} from './types';

const BASE = '/api/puzzlerush';

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
  /** The current guest run's token, if any. */
  guestToken?: string | null;
}

export function localTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Almaty';
  } catch {
    return 'Asia/Almaty';
  }
}

async function request<T>(
  auth: RushAuth,
  path: string,
  init: { method?: 'GET' | 'POST'; body?: unknown; query?: Record<string, string> } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = await auth.getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  else if (auth.guestToken) headers['X-Guest-Token'] = auth.guestToken;
  if (init.body !== undefined) headers['Content-Type'] = 'application/json';

  const params = new URLSearchParams({ tz: localTimeZone(), ...init.query });
  const res = await fetch(`${BASE}${path}?${params}`, {
    method: init.method ?? 'GET',
    headers,
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (!res.ok) throw new RushApiError(res.status, data);
  return data as T;
}

export const rushApi = {
  createRun: (auth: RushAuth, mode: RushMode) =>
    request<CreateRunResponse>(auth, '/runs', { method: 'POST', body: { mode } }),
  move: (auth: RushAuth, runId: string, uci: string) =>
    request<MoveResponse>(auth, `/runs/${runId}/move`, { method: 'POST', body: { uci } }),
  quit: (auth: RushAuth, runId: string) =>
    request<QuitResponse>(auth, `/runs/${runId}/quit`, { method: 'POST', body: {} }),
  getRun: (auth: RushAuth, runId: string) => request<RunSummary>(auth, `/runs/${runId}`),
  bests: (auth: RushAuth) => request<BestsResponse>(auth, '/bests'),
  leaderboard: (auth: RushAuth, mode: RushMode, period: RushPeriod, scope: RushScope) =>
    request<LeaderboardResponse>(auth, '/leaderboard', { query: { mode, period, scope } }),
};
