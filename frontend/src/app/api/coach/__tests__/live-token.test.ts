import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock Clerk auth
vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

// Mock @google/genai so no real network call happens.
const createMock = vi.fn();
vi.mock('@google/genai', () => ({
  GoogleGenAI: class {
    authTokens = { create: createMock };
  },
  Modality: { AUDIO: 'AUDIO' },
}));

import { auth } from '@clerk/nextjs/server';

const makeRequest = (body?: unknown) =>
  new Request('http://localhost:3000/api/coach/live-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

describe('POST /api/coach/live-token', () => {
  const originalKey = process.env.GEMINI_API_KEY;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    if (originalKey === undefined) {
      delete process.env.GEMINI_API_KEY;
    } else {
      process.env.GEMINI_API_KEY = originalKey;
    }
    vi.restoreAllMocks();
  });

  it('returns 401 when not authenticated', async () => {
    (auth as any).mockResolvedValue({ userId: null });

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({}));

    expect(response.status).toBe(401);
    const data = await response.json();
    expect(data.error).toBe('Unauthorized');
  });

  it('returns 500 when GEMINI_API_KEY is unset', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    delete process.env.GEMINI_API_KEY;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({}));

    expect(response.status).toBe(500);
    const data = await response.json();
    expect(data.error).toBe('Live coach not configured');
  });

  it('returns 200 with token, model and expiresAt when mint succeeds', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ tools: [] }) })) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(
      makeRequest({ fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' }),
    );

    expect(response.status).toBe(200);
    const data = await response.json();
    expect(data.token).toBe('ephemeral-token-xyz');
    expect(data.model).toBe('gemini-3.1-flash-live-preview');
    expect(typeof data.expiresAt).toBe('string');
    expect(createMock).toHaveBeenCalledTimes(1);
  });

  it('returns 502 when the mint call rejects', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockRejectedValue(new Error('google boom'));
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ tools: [] }) })) as any;
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({}));

    expect(response.status).toBe(502);
    const data = await response.json();
    expect(data.error).toBe('Failed to start live session');
    errorSpy.mockRestore();
  });

  // ── Shared conversation memory injection ────────────────────────────────────

  const systemInstructionFromMint = () => {
    const call = createMock.mock.calls[0][0];
    return call.config.liveConnectConstraints.config.systemInstruction as string;
  };

  it('injects a conversation recap from Hermes when session_id is present', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const fetchSpy = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: [] }) };
      }
      return {
        ok: true,
        json: async () => ({
          messages: [
            { role: 'user', content: 'How do I attack the king?', source: 'text' },
            { role: 'assistant', content: 'Open lines first.', source: 'text' },
            { role: 'user', content: 'Like this?', source: 'voice' },
          ],
        }),
      };
    });
    global.fetch = fetchSpy as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ session_id: 'sess_1' }));

    expect(response.status).toBe(200);
    // Fetched the last 20 messages for this session, scoped by user.
    const recapCall = fetchSpy.mock.calls.find((c: any[]) =>
      String(c[0]).includes('/messages'),
    );
    expect(recapCall).toBeTruthy();
    const [url, opts] = recapCall as any[];
    expect(url).toContain('/api/coach/sessions/sess_1/messages');
    expect(url).toContain('limit=20');
    expect(opts.headers['X-User-Id']).toBe('user_123');

    const instruction = systemInstructionFromMint();
    expect(instruction).toContain('continuing an ongoing coaching conversation');
    expect(instruction).toContain('How do I attack the king?');
    expect(instruction).toContain('Open lines first.');
    // Voice-sourced lines may be tagged.
    expect(instruction).toContain('[user (spoken)] Like this?');
  });

  it('does not fetch the recap when no session_id is provided', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const fetchSpy = vi.fn(async () => ({ ok: true, json: async () => ({ tools: [] }) }));
    global.fetch = fetchSpy as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));

    expect(response.status).toBe(200);
    // Tools are still fetched, but no session message recap.
    const recapCall = fetchSpy.mock.calls.find((c: any[]) =>
      String(c[0]).includes('/messages'),
    );
    expect(recapCall).toBeUndefined();
    expect(systemInstructionFromMint()).not.toContain(
      'continuing an ongoing coaching conversation',
    );
  });

  // ── Tool declaration embedding ──────────────────────────────────────────────

  const configFromMint = () =>
    createMock.mock.calls[0][0].config.liveConnectConstraints.config;

  it('embeds tool functionDeclarations from Hermes into the token constraints', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const decls = [
      { name: 'board_control', description: 'control board', parameters: { type: 'object' } },
    ];
    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: decls }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));

    expect(response.status).toBe(200);
    const config = configFromMint();
    expect(config.tools).toEqual([{ functionDeclarations: decls }]);
    expect(config.systemInstruction).toContain('You have tools.');
  });

  it('enables sessionResumption in the token constraints so the server issues handles', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ tools: [] }) })) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));

    expect(response.status).toBe(200);
    expect(configFromMint().sessionResumption).toEqual({});
  });

  it('mints the token without tools (still 200) when the tools fetch fails', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    global.fetch = vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) })) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));

    expect(response.status).toBe(200);
    expect(configFromMint().tools).toBeUndefined();
    warnSpy.mockRestore();
  });

  it('falls back to no recap (still 200) when the Hermes fetch fails', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    global.fetch = vi.fn().mockRejectedValue(new Error('hermes down')) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ session_id: 'sess_1' }));

    // Voice must still start even if Hermes is unreachable.
    expect(response.status).toBe(200);
    expect(systemInstructionFromMint()).not.toContain(
      'continuing an ongoing coaching conversation',
    );
    errorSpy.mockRestore();
  });

  // ── Recap capping (latency: ≤10 msgs, 200 chars/msg, ≤2KB, no markdown) ─────

  // Route Hermes fetches: recap messages via /messages, empty tools otherwise.
  const routeRecap = (messages: unknown[]) =>
    vi.fn(async (url: string) => {
      if (String(url).includes('/messages')) {
        return { ok: true, json: async () => ({ messages }) };
      }
      return { ok: true, json: async () => ({ tools: [] }) };
    });

  // Extract just the recap block from the system instruction for tight assertions.
  const recapBlockFromMint = () => {
    const instruction = systemInstructionFromMint();
    const start = instruction.indexOf('\n\nYou are continuing');
    if (start === -1) return '';
    return instruction.slice(start);
  };

  it('keeps at most 10 recap messages (the most recent ones)', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const messages = Array.from({ length: 15 }, (_, i) => ({
      role: i % 2 === 0 ? 'user' : 'assistant',
      content: `message number ${i}`,
      source: 'text',
    }));
    global.fetch = routeRecap(messages) as any;

    const { POST } = await import('../live-token/route');
    await POST(makeRequest({ session_id: 'sess_1' }));

    const block = recapBlockFromMint();
    const lineCount = (block.match(/\[(user|coach)/g) || []).length;
    expect(lineCount).toBe(10);
    // Oldest were dropped; newest kept.
    expect(block).toContain('message number 14');
    expect(block).not.toContain('message number 4');
  });

  it('truncates each recap message to 200 characters', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const messages = [{ role: 'user', content: 'A'.repeat(300), source: 'text' }];
    global.fetch = routeRecap(messages) as any;

    const { POST } = await import('../live-token/route');
    await POST(makeRequest({ session_id: 'sess_1' }));

    const block = recapBlockFromMint();
    expect(block).toContain('A'.repeat(200));
    expect(block).not.toContain('A'.repeat(201));
  });

  it('caps the total recap block at 2KB', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const messages = Array.from({ length: 10 }, (_, i) => ({
      role: 'user',
      content: `${i} ` + 'X'.repeat(500),
      source: 'text',
    }));
    global.fetch = routeRecap(messages) as any;

    const { POST } = await import('../live-token/route');
    await POST(makeRequest({ session_id: 'sess_1' }));

    const block = recapBlockFromMint();
    expect(Buffer.byteLength(block, 'utf8')).toBeLessThanOrEqual(2048);
  });

  it('strips markdown and tool-call noise from recap messages', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const messages = [
      {
        role: 'assistant',
        content: '**Bold** and `code` and\n```json\n{"tool":"x"}\n```\n# Heading',
        source: 'text',
      },
    ];
    global.fetch = routeRecap(messages) as any;

    const { POST } = await import('../live-token/route');
    await POST(makeRequest({ session_id: 'sess_1' }));

    const block = recapBlockFromMint();
    expect(block).not.toContain('**');
    expect(block).not.toContain('```');
    expect(block).not.toContain('`');
    expect(block).not.toContain('#');
    expect(block).not.toContain('{"tool":"x"}');
    expect(block).toContain('Bold');
  });

  // ── Voice tool allowlist ────────────────────────────────────────────────────

  it('filters the toolset down to the voice allowlist, dropping import/account tools', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const decls = [
      { name: 'board_control' },
      { name: 'analyze_position' },
      { name: 'get_position_stats' },
      { name: 'get_opening_stats' },
      { name: 'search_master_games' },
      // Excluded: import / sync / link / account tools.
      { name: 'chesscom_game_import' },
      { name: 'lichess_game_import' },
      { name: 'link_platform' },
      { name: 'get_user_games' },
      { name: 'get_user_progress' },
    ];
    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: decls }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));

    expect(response.status).toBe(200);
    const kept = configFromMint().tools[0].functionDeclarations.map(
      (d: any) => d.name,
    );
    expect(kept).toContain('board_control');
    expect(kept).toContain('analyze_position');
    expect(kept).toContain('search_master_games');
    expect(kept).not.toContain('chesscom_game_import');
    expect(kept).not.toContain('lichess_game_import');
    expect(kept).not.toContain('link_platform');
    expect(kept).not.toContain('get_user_games');
    expect(kept.length).toBeLessThanOrEqual(8);
  });

  it('embeds no tools (and no tool guidance) when none survive the allowlist', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    const decls = [{ name: 'chesscom_game_import' }, { name: 'sync_ratings' }];
    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: decls }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));

    expect(response.status).toBe(200);
    expect(configFromMint().tools).toBeUndefined();
    expect(configFromMint().systemInstruction).not.toContain('You have tools.');
  });

  it('adds the acknowledge-before-tool guidance when voice tools are present', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: [{ name: 'board_control' }] }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    await POST(makeRequest({ fen: 'somefen' }));

    const instruction = systemInstructionFromMint();
    expect(instruction).toContain('You have tools.');
    // Must instruct a spoken acknowledgment before the tool call.
    expect(instruction.toLowerCase()).toContain('acknowledgment');
  });

  // ── Parallelized Hermes fetches ─────────────────────────────────────────────

  it('fetches the voice prompt, recap and tools concurrently (not serialized)', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    let inFlight = 0;
    let maxInFlight = 0;
    global.fetch = vi.fn(async (url: string) => {
      inFlight += 1;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await new Promise((r) => setTimeout(r, 5));
      inFlight -= 1;
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: [] }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    await POST(makeRequest({ session_id: 'sess_1' }));

    // All three Hermes calls (voice/prompt, recap, tools) overlapped.
    expect(maxInFlight).toBe(3);
  });

  // ── Single-source prompt + mint rate limit (Tasks 2/3 & 1) ──────────────────

  it('uses the single-source Hermes prompt when /voice/prompt returns 200', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/voice/prompt')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            system_prompt: 'HERMES SINGLE SOURCE PROMPT for the spoken coach.',
            profile_context: 'Student rating: 1500',
          }),
        };
      }
      if (String(url).includes('/api/coach/tools')) {
        return { ok: true, json: async () => ({ tools: [] }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({ fen: 'somefen' }));
    expect(response.status).toBe(200);
    // The Hermes-rendered prompt is locked into the token, not the hardcoded one.
    expect(systemInstructionFromMint()).toContain('HERMES SINGLE SOURCE PROMPT');
  });

  it('returns 429 and does NOT mint when Hermes rate-limits the mint', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/voice/prompt')) {
        return {
          ok: false,
          status: 429,
          json: async () => ({ detail: { retry_after: 120 } }),
        };
      }
      return { ok: true, json: async () => ({ tools: [], messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({}));
    expect(response.status).toBe(429);
    const data = await response.json();
    expect(data.error).toBe('rate_limited');
    expect(data.retry_after).toBe(120);
    // The Gemini mint must never have been called.
    expect(createMock).not.toHaveBeenCalled();
  });

  it('falls back to the hardcoded prompt when /voice/prompt is unreachable', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    process.env.GEMINI_API_KEY = 'AQ.test-key';
    createMock.mockResolvedValue({ name: 'ephemeral-token-xyz' });

    global.fetch = vi.fn(async (url: string) => {
      if (String(url).includes('/api/coach/voice/prompt')) {
        throw new Error('hermes down');
      }
      return { ok: true, json: async () => ({ tools: [], messages: [] }) };
    }) as any;

    const { POST } = await import('../live-token/route');
    const response = await POST(makeRequest({}));
    expect(response.status).toBe(200);
    // Hardcoded fallback persona is used (voice must never break).
    expect(systemInstructionFromMint()).toContain("Chesster's chess coach");
  });
});
