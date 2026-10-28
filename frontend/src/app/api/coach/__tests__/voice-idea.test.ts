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

const FEN = 'r1b1k1nr/pppp1ppp/2n5/2b1p3/4P2q/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 0 5';

const makeRequest = (body?: unknown) =>
  new Request('http://localhost:3000/api/coach/voice/idea', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

describe('POST /api/coach/voice/idea', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    (auth as any).mockResolvedValue({ userId: null });
    const { POST } = await import('../voice/idea/route');
    const res = await POST(makeRequest({ text: 'а если Rg1?', fen: FEN }) as any);
    expect(res.status).toBe(401);
  });

  it('returns 400 without the words or the board', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const { POST } = await import('../voice/idea/route');
    expect((await POST(makeRequest({ fen: FEN }) as any)).status).toBe(400);
    expect((await POST(makeRequest({ text: 'а если Rg1?' }) as any)).status).toBe(400);
  });

  it('forwards the words, the board and the game flag to Hermes with the Clerk user id', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const hermes = { note: '[Idea] The student names a move: Rg1 — legal. …', moves: [{ san: 'Rg1', legal: true, verdict: 'legal' }], fens: [] };
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => hermes }));
    global.fetch = fetchMock as any;

    const { POST } = await import('../voice/idea/route');
    const res = await POST(makeRequest({ text: 'а что если поставить ладью на g1?', fen: FEN, live_game: true }) as any);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual(hermes);

    const [url, opts] = fetchMock.mock.calls[0] as any[];
    expect(url).toMatch(/\/api\/coach\/voice\/idea$/);
    expect(opts.headers['X-User-Id']).toBe('user_1');
    expect(opts.headers['x-subscription-tier']).toBe('pro');
    expect(JSON.parse(opts.body)).toEqual({ text: 'а что если поставить ладью на g1?', fen: FEN, live_game: true });
  });

  // 28.10: the proxy dropped the pgn the hook sends outside a game, so «на 8-м ходу…» was judged on the final position.
  it('forwards the game on the board (pgn) outside a live game, bounded in length', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const fetchMock = vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ note: null, moves: [], fens: [] }) }));
    global.fetch = fetchMock as any;
    const pgn = '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5 4. c3 Nf6 5. d4 exd4 6. cxd4 Bb4+ 7. Nc3 Nxe4 8. O-O Nxc3';

    const { POST } = await import('../voice/idea/route');
    await POST(makeRequest({ text: 'а что если бы на 8-м ходу я сыграл Bxf7+?', fen: FEN, pgn }) as any);
    const sent = JSON.parse((fetchMock.mock.calls[0] as any[])[1].body);
    expect(sent).toEqual({ text: 'а что если бы на 8-м ходу я сыграл Bxf7+?', fen: FEN, live_game: false, pgn });

    await POST(makeRequest({ text: 'а если Rg1?', fen: FEN, pgn: 'x'.repeat(50000) }) as any);
    expect(JSON.parse((fetchMock.mock.calls[1] as any[])[1].body).pgn).toHaveLength(20000);

    await POST(makeRequest({ text: 'а если Rg1?', fen: FEN, pgn: 42 }) as any);
    expect(JSON.parse((fetchMock.mock.calls[2] as any[])[1].body).pgn).toBeUndefined();
  });

  it('answers 502 when Hermes is unreachable', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    global.fetch = vi.fn(async () => {
      throw new Error('connect ECONNREFUSED');
    }) as any;
    const { POST } = await import('../voice/idea/route');
    const res = await POST(makeRequest({ text: 'а если Rg1?', fen: FEN }) as any);
    expect(res.status).toBe(502);
  });
});
