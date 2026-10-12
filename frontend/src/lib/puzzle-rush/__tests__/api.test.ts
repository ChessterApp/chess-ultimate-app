import { describe, it, expect, vi, beforeEach } from 'vitest';
import { rushApi, RushApiError } from '../api';

const fetchMock = vi.fn();

function respond(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: new URL(url as string, 'http://x'), init: init as RequestInit };
}

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
});

describe('rushApi', () => {
  it('sends the Clerk bearer token for signed-in calls (and no guest header)', async () => {
    respond(201, { run_id: 'r1' });
    await rushApi.createRun({ getToken: async () => 'jwt-123', guestToken: 'g' }, '5min');
    const { url, init } = lastCall();
    expect(url.pathname).toBe('/api/puzzlerush/runs');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ mode: '5min' });
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer jwt-123');
    expect(headers['X-Guest-Token']).toBeUndefined();
  });

  it('sends X-Guest-Token for guest calls', async () => {
    respond(200, { result: 'correct' });
    await rushApi.move({ getToken: async () => null, guestToken: 'guest-abc' }, 'run-1', 'e2e4');
    const { url, init } = lastCall();
    expect(url.pathname).toBe('/api/puzzlerush/runs/run-1/move');
    const headers = init.headers as Record<string, string>;
    expect(headers['X-Guest-Token']).toBe('guest-abc');
    expect(headers.Authorization).toBeUndefined();
    expect(JSON.parse(init.body as string)).toEqual({ uci: 'e2e4' });
  });

  it('passes the local time zone and leaderboard params as query', async () => {
    respond(200, { entries: [] });
    await rushApi.leaderboard({ getToken: async () => null }, '3min', 'weekly', 'global');
    const { url, init } = lastCall();
    expect(url.pathname).toBe('/api/puzzlerush/leaderboard');
    expect(url.searchParams.get('mode')).toBe('3min');
    expect(url.searchParams.get('period')).toBe('weekly');
    expect(url.searchParams.get('scope')).toBe('global');
    expect(url.searchParams.get('tz')).toBeTruthy();
    expect(init.method).toBe('GET');
  });

  it('surfaces the 409 run_over body (with results) and never retries', async () => {
    respond(409, { error: 'run_over', end_reason: 'timeout', results: { score: 3 } });
    const err = await rushApi.move({ getToken: async () => null, guestToken: 'g' }, 'r', 'e2e4').catch((e) => e);
    expect(err).toBeInstanceOf(RushApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe('run_over');
    expect(err.body.results).toEqual({ score: 3 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('maps a non-JSON error to an http_<status> code', async () => {
    fetchMock.mockResolvedValueOnce(new Response('oops', { status: 502 }));
    const err = await rushApi.bests({ getToken: async () => 't' }).catch((e) => e);
    expect(err.code).toBe('http_502');
  });
});
