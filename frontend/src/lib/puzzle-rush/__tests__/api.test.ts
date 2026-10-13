import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createRushApi, rushApi, RushApiError } from '../api';
import type { FinishRequest } from '../types';

const fetchMock = vi.fn();

function respond(status: number, body: unknown) {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }));
}

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  return { url: new URL(url as string, 'http://x'), init: init as RequestInit };
}

const FINISH: FinishRequest = {
  run_id: '11111111-2222-4333-8444-555555555555', mode: '5min', seed: '0123456789abcdef',
  started_at: '2026-10-12T10:00:00.000Z', ended_at: '2026-10-12T10:05:00.000Z', end_reason: 'timeout', attempts: [],
};

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
});

describe('rushApi', () => {
  it('pack: public GET with only seed/from/count (stable, cacheable URL)', async () => {
    respond(200, { seed: 'abc', from: 40, count: 0, puzzles: [] });
    await rushApi.pack('0123456789abcdef', 40);
    const { url, init } = lastCall();
    expect(url.pathname).toBe('/api/puzzlerush/pack');
    expect(Object.fromEntries(url.searchParams)).toEqual({ seed: '0123456789abcdef', from: '40', count: '40' });
    expect(init.method).toBe('GET');
    expect(init.headers).toEqual({});
  });

  it('finish: POSTs the run with the Clerk bearer token and the local time zone', async () => {
    respond(200, { run_id: FINISH.run_id, score: 0 });
    await rushApi.finish({ getToken: async () => 'jwt-123' }, FINISH);
    const { url, init } = lastCall();
    expect(url.pathname).toBe('/api/puzzlerush/runs/finish');
    expect(url.searchParams.get('tz')).toBeTruthy();
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual(FINISH);
    expect(init.headers).toMatchObject({ Authorization: 'Bearer jwt-123', 'Content-Type': 'application/json' });
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
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it('schoolLeaderboard: survival school/branch board with period and optional student_id', async () => {
    respond(200, { entries: [] });
    await rushApi.schoolLeaderboard({ getToken: async () => 't' }, 'branch', 'month', 'stu-2');
    let { url } = lastCall();
    expect(url.pathname).toBe('/api/puzzlerush/leaderboard');
    expect(url.searchParams.get('mode')).toBe('survival');
    expect(url.searchParams.get('scope')).toBe('branch');
    expect(url.searchParams.get('period')).toBe('month');
    expect(url.searchParams.get('student_id')).toBe('stu-2');

    respond(200, { entries: [] });
    await rushApi.schoolLeaderboard({ getToken: async () => 't' }, 'school', 'all');
    ({ url } = lastCall());
    expect(url.searchParams.get('scope')).toBe('school');
    expect(url.searchParams.get('period')).toBe('all');
    expect(url.searchParams.has('student_id')).toBe(false);
  });

  it('schoolClaim: POSTs the student to the run and returns the school outcome', async () => {
    respond(200, { school: { status: 'pushed', student_id: 'stu-1', beaten: ['week'] } });
    const res = await rushApi.schoolClaim({ getToken: async () => 'jwt' }, FINISH.run_id, 'stu-1');
    const { url, init } = lastCall();
    expect(url.pathname).toBe(`/api/puzzlerush/runs/${FINISH.run_id}/school-claim`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ student_id: 'stu-1' });
    expect(init.headers).toMatchObject({ Authorization: 'Bearer jwt' });
    expect(res).toEqual({ status: 'pushed', student_id: 'stu-1', beaten: ['week'] });
  });

  it('surfaces the error code + body and never retries', async () => {
    respond(409, { error: 'conflict' });
    const err = await rushApi.finish({ getToken: async () => 't' }, FINISH).catch((e) => e);
    expect(err).toBeInstanceOf(RushApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe('conflict');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('maps a non-JSON error to an http_<status> code', async () => {
    fetchMock.mockResolvedValueOnce(new Response('oops', { status: 502 }));
    const err = await rushApi.bests({ getToken: async () => 't' }).catch((e) => e);
    expect(err.code).toBe('http_502');
  });

  it('createRushApi takes an absolute base for the mobile app', async () => {
    respond(200, { puzzles: [] });
    await createRushApi('https://chesster.io/api/puzzlerush').pack('0123456789abcdef');
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/^https:\/\/chesster\.io\/api\/puzzlerush\/pack\?seed=/);
  });
});
