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

const FEN = 'r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R b KQkq - 0 5';
const PGN = '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. Nc3 Nf6 5. d3';

const makeRequest = (body?: unknown) =>
  new Request('http://localhost:3000/api/coach/voice/check', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

describe('POST /api/coach/voice/check', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    (auth as any).mockResolvedValue({ userId: null });
    const { POST } = await import('../voice/check/route');
    expect((await POST(makeRequest({ text: 'Партия шла так: 1. e4 e5' }) as any)).status).toBe(401);
  });

  it('returns 400 without the words', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const { POST } = await import('../voice/check/route');
    expect((await POST(makeRequest({ fen: FEN }) as any)).status).toBe(400);
  });

  // 28.10: Hermes reads the pgn to know the history of a loaded game; without it a true recap was "corrected" aloud.
  it('forwards text, fen, pgn, question and session_id to Hermes with the Clerk user id', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ issues: [] }) }));
    global.fetch = fetchMock as any;

    const { POST } = await import('../voice/check/route');
    const body = { text: 'Партия шла так: 1. e4 e5 2. Кf3 Кc6 3. Сc4 Сc5', fen: FEN, pgn: PGN, question: 'как шла партия?', session_id: 'sess_1' };
    const res = await POST(makeRequest(body) as any);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ issues: [] });

    const [url, opts] = fetchMock.mock.calls[0] as any[];
    expect(url).toMatch(/\/api\/coach\/voice\/check$/);
    expect(opts.headers['X-User-Id']).toBe('user_1');
    expect(opts.headers['x-subscription-tier']).toBe('pro');
    expect(JSON.parse(opts.body)).toEqual(body);
  });

  // 30.10: every claim of an answer goes to the board check; the engine only for the answer's few engine checks.
  it('forwards the sentences before and the engine flag, and returns whether the engine was asked', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ issues: [], engine: false }) }));
    global.fetch = fetchMock as any;

    const { POST } = await import('../voice/check/route');
    const res = await POST(makeRequest({ text: 'Больше ничего не висит.', fen: FEN, previous: 'Под ударом слон c4.', engine: false }) as any);
    expect(await res.json()).toEqual({ issues: [], engine: false });
    expect(JSON.parse((fetchMock.mock.calls[0] as any[])[1].body)).toMatchObject({ previous: 'Под ударом слон c4.', engine: false });
    await POST(makeRequest({ text: 'Больше ничего не висит.', engine: 'no' }) as any);
    expect(JSON.parse((fetchMock.mock.calls[1] as any[])[1].body).engine).toBeUndefined();
  });

  it('bounds the pgn it forwards', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ issues: [] }) }));
    global.fetch = fetchMock as any;

    const { POST } = await import('../voice/check/route');
    await POST(makeRequest({ text: 'Партия шла так: 1. e4 e5', pgn: 'x'.repeat(50000) }) as any);
    expect(JSON.parse((fetchMock.mock.calls[0] as any[])[1].body).pgn).toHaveLength(20000);
  });

  it('answers 502 when Hermes is unreachable', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    global.fetch = vi.fn(async () => {
      throw new Error('connect ECONNREFUSED');
    }) as any;
    const { POST } = await import('../voice/check/route');
    expect((await POST(makeRequest({ text: 'Партия шла так: 1. e4 e5' }) as any)).status).toBe(502);
  });
});
