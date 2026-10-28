/**
 * The /position, /game, /puzzle analysis seam (28.10): a click-analysis with
 * master stats passed Hermes' 2000-character query cap and got 400; the proxies
 * dropped context_note and the subscription tier, and the stream proxy hid
 * Hermes' error text behind «Hermes error: N».
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/require-api-access', () => ({ requireApiAccess: async () => null }));

import { auth } from '@clerk/nextjs/server';
import { NextRequest } from 'next/server';
import { getOpeningStatSpeech, type MasterGames } from '@/lib/openingdatabase/helper';
import { getChessDBSpeech } from '@/components/tabs/Chessdb';
import {
  ANALYSIS_CONTEXT_MAX,
  ANALYSIS_QUERY_MAX,
  buildClickAnalysisRequest,
} from '@/lib/coach/click-analysis';

const FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// What /api/explorer/masters returns for the start position (12 moves, 3 games).
const SANS = ['e4', 'd4', 'Nf3', 'c4', 'g3', 'b3', 'f4', 'Nc3', 'b4', 'e3', 'd3', 'a3'];
const MASTERS = {
  opening: null,
  white: 500000,
  draws: 700000,
  black: 350000,
  moves: SANS.map((san, i) => ({
    uci: 'e2e4', san, white: 1000 - i * 60, draws: 1200 - i * 60, black: 800 - i * 50, averageRating: 2410 + i,
  })),
  topGames: [1, 2, 3].map(() => ({
    id: 'abcdEFGH', white: { name: 'Carlsen, Magnus', rating: 2863 }, black: { name: 'Caruana, Fabiano', rating: 2820 },
    month: '2019-03', year: 2019, winner: 'white',
  })),
} as unknown as MasterGames;

const CHESSDB = SANS.map((san, i) => ({
  uci: 'e2e4', san, score: String(30 - i), winrate: '51.2', rank: '2', note: '! (12-03)',
}));
const ENGINE = `Depth: 18\n${[1, 2, 3]
  .map((i) => `  Line ${i}: +0.3${i}\n    Moves: 1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6`)
  .join('\n\n')}`;

/** Hermes' own checks (server.py _validate_analysis_body) as a fetch stand-in. */
function hermesStandIn(seen: { body?: Record<string, unknown>; headers?: Record<string, string> }) {
  return vi.fn(async (_url: string, opts: { body: string; headers: Record<string, string> }) => {
    const body = JSON.parse(opts.body);
    seen.body = body;
    seen.headers = opts.headers;
    const reject = (error: string) => ({ ok: false, status: 400, json: async () => ({ success: false, error }) });
    if (typeof body.query !== 'string' || body.query.length > ANALYSIS_QUERY_MAX) {
      return reject('Query too long (max 2000 characters)');
    }
    if (body.context_note !== undefined && String(body.context_note).length > ANALYSIS_CONTEXT_MAX) {
      return reject('Context too long');
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ success: true, response: 'Solid.', board_actions: [], conversation_id: 'c1', tokens_used: 2 }),
    };
  });
}

function post(url: string, body: unknown) {
  return new NextRequest(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

describe('analysis seam (28.10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    process.env.COACH_DEFAULT_TIER = 'premium';
  });
  afterEach(() => {
    delete process.env.COACH_DEFAULT_TIER;
    vi.restoreAllMocks();
  });

  it('a realistic opening-move click with master stats reaches the model through the route', async () => {
    const req = buildClickAnalysisRequest({
      type: 'openingMove',
      currentFen: FEN,
      move: MASTERS.moves[0],
      openingData: MASTERS,
      grounding: {
        openingSpeech: getOpeningStatSpeech(MASTERS),
        databaseSpeech: getChessDBSpeech(CHESSDB),
        engineAnalysis: ENGINE,
      },
    });
    // The old single query (request + grounding) was well over the cap.
    expect(req.query.length + (req.context_note ?? '').length).toBeGreaterThan(ANALYSIS_QUERY_MAX);

    const seen: { body?: Record<string, unknown> } = {};
    global.fetch = hermesStandIn(seen) as any;
    const { POST } = await import('../analysis/route');
    const res = await POST(post('http://localhost/api/coach/analysis', { ...req, context_type: 'position' }) as any);

    expect(res.status).toBe(200);
    expect((await res.json()).response).toBe('Solid.');
    // The grounding was not lost on the way: the model still gets the stats.
    expect(String(seen.body?.context_note)).toContain('Carlsen, Magnus');
    expect(String(seen.body?.context_note)).toContain('<engine_analysis>');
  });

  it('the stream proxy forwards context_note too', async () => {
    const seen: { body?: Record<string, unknown> } = {};
    global.fetch = vi.fn(async (_u: string, opts: { body: string }) => {
      seen.body = JSON.parse(opts.body);
      const enc = new TextEncoder();
      return {
        ok: true,
        status: 200,
        body: new ReadableStream({
          start(c) {
            c.enqueue(enc.encode(`data: ${JSON.stringify({ done: true, conversation_id: 'c', tokens_used: 1 })}\n\n`));
            c.close();
          },
        }),
      };
    }) as any;
    const { POST } = await import('../analysis/stream/route');
    const res = await POST(post('http://localhost/api/coach/analysis/stream', { fen: FEN, query: 'q', context_note: 'ctx' }) as any);
    await res.text();
    expect(seen.body?.context_note).toBe('ctx');
  });

  it('both analysis proxies forward x-subscription-tier like the coach proxies', async () => {
    const seen: { headers?: Record<string, string> } = {};
    global.fetch = hermesStandIn(seen) as any;
    const { POST } = await import('../analysis/route');
    await POST(post('http://localhost/api/coach/analysis', { fen: FEN, query: 'q' }) as any);
    expect(seen.headers?.['x-subscription-tier']).toBe('premium');

    let streamHeaders: Record<string, string> | undefined;
    global.fetch = vi.fn(async (_u: string, opts: { headers: Record<string, string> }) => {
      streamHeaders = opts.headers;
      return { ok: true, status: 200, body: new ReadableStream({ start: (c) => c.close() }) };
    }) as any;
    const stream = await import('../analysis/stream/route');
    const res = await stream.POST(post('http://localhost/api/coach/analysis/stream', { fen: FEN, query: 'q' }) as any);
    await res.text();
    expect(streamHeaders?.['x-subscription-tier']).toBe('premium');
  });

  it('the stream proxy passes Hermes’ readable error and status, not «Hermes error: N»', async () => {
    const hermesBody = {
      success: false,
      error: 'Rate limit exceeded for free tier. Limit: 30 requests per minute.',
      rate_limited: true,
    };
    global.fetch = vi.fn(async () => ({
      ok: false,
      status: 429,
      json: async () => hermesBody,
      text: async () => JSON.stringify(hermesBody),
    })) as any;
    const { POST } = await import('../analysis/stream/route');
    const res = await POST(post('http://localhost/api/coach/analysis/stream', { fen: FEN, query: 'q' }) as any);

    expect(res.status).toBe(429);
    const body = await res.json();
    expect(body.error).toBe(hermesBody.error);
    expect(body.rate_limited).toBe(true);
  });
});
