import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));
vi.mock('@/lib/coach-access', () => ({
  requireCoachAccess: vi.fn(async () => null),
}));
vi.mock('@/lib/subscription-tier', () => ({
  resolveUserTier: vi.fn(async () => 'pro'),
}));

import { auth } from '@clerk/nextjs/server';

const FEN = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2';
const makeRequest = (body: unknown) =>
  new Request('http://localhost:3000/api/coach/voice/engine-note', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

describe('POST /api/coach/voice/engine-note', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (auth as any).mockResolvedValue({ userId: 'user_1' });
  });

  // Alexander 27.10: the session was dropped here, Hermes never saw the game, and every game position got the plain
  // engine line with the best move — which the voice coach announced as its own move.
  it('forwards the session, so Hermes answers a game position with the game facts', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ fen: FEN, note: null, kind: 'game' }) }));
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/engine-note/route');
    const res = await POST(makeRequest({ fen: FEN, session_id: 'sess-1' }) as any);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ fen: FEN, note: null, kind: 'game' });
    const [url, opts] = fetchMock.mock.calls[0] as any[];
    expect(url).toMatch(/\/api\/coach\/voice\/engine-note$/);
    expect(opts.headers['X-User-Id']).toBe('user_1');
    expect(JSON.parse(opts.body)).toEqual({ fen: FEN, session_id: 'sess-1' });
  });

  it('sends no session when there is none (or it is not a string)', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({}) }));
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/engine-note/route');
    await POST(makeRequest({ fen: FEN }) as any);
    await POST(makeRequest({ fen: FEN, session_id: 42 }) as any);
    expect(fetchMock.mock.calls.map((c: any[]) => JSON.parse(c[1].body))).toEqual([{ fen: FEN }, { fen: FEN }]);
  });
});
