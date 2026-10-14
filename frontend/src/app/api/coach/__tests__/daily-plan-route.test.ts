import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/require-api-access', () => ({ requireApiAccess: async () => null }));

import { auth } from '@clerk/nextjs/server';
import { GET } from '../daily-plan/route';

const PLAN = { kind: 'daily_plan', cards: [{ type: 'weak_spot', puzzles: 5 }, { type: 'play_coach' }] };

describe('GET /api/coach/daily-plan', () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('401 without a user, Hermes never called', async () => {
    vi.mocked(auth).mockResolvedValue({ userId: null } as never);
    expect((await GET()).status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('forwards to Hermes with the user id stamped server-side', async () => {
    vi.mocked(auth).mockResolvedValue({ userId: 'user_p' } as never);
    fetchMock.mockResolvedValue(new Response(JSON.stringify(PLAN), { status: 200 }));
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(PLAN);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/api\/coach\/daily-plan$/);
    expect(init.method).toBe('GET');
    expect(init.headers['X-User-Id']).toBe('user_p');
  });

  it('passes a Hermes error through', async () => {
    vi.mocked(auth).mockResolvedValue({ userId: 'user_p' } as never);
    fetchMock.mockResolvedValue(new Response('{}', { status: 503 }));
    expect((await GET()).status).toBe(503);
  });
});
