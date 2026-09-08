import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock Clerk auth
vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

describe('Coach API Routes', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('POST /api/coach/chat', () => {
    it('returns 401 when not authenticated', async () => {
      (auth as any).mockResolvedValue({ userId: null });

      const { POST } = await import('../../coach/chat/route');

      const request = new Request('http://localhost:3000/api/coach/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'test' }),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(401);

      const data = await response.json();
      expect(data.error).toBe('Unauthorized');
    });

    it('returns 400 when message is missing', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });

      const { POST } = await import('../../coach/chat/route');

      const request = new Request('http://localhost:3000/api/coach/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(400);

      const data = await response.json();
      expect(data.error).toBe('Missing message');
    });

    it('returns SSE stream headers on valid request', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });

      // Mock fetch to Hermes returning JSON
      global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        headers: new Headers({ 'content-type': 'application/json' }),
        json: async () => ({
          message: 'Hello!',
          board_actions: [],
          session_id: 'session_1',
        }),
      }) as any;

      const { POST } = await import('../../coach/chat/route');

      const { NextRequest } = await import('next/server');
      const request = new NextRequest('http://localhost:3000/api/coach/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: 'Analyze this position', fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' }),
      });

      const response = await POST(request as any);
      expect(response.headers.get('Content-Type')).toBe('text/event-stream');
      expect(response.headers.get('Cache-Control')).toBe('no-cache');
    });
  });

  describe('GET /api/coach/sessions', () => {
    it('returns 401 when not authenticated', async () => {
      (auth as any).mockResolvedValue({ userId: null });

      const { GET } = await import('../../coach/sessions/route');

      const response = await GET();
      expect(response.status).toBe(401);

      const data = await response.json();
      expect(data.error).toBe('Unauthorized');
    });
  });

  describe('GET /api/coach/profile', () => {
    it('returns 401 when not authenticated', async () => {
      (auth as any).mockResolvedValue({ userId: null });

      const { GET } = await import('../../coach/profile/route');

      const response = await GET();
      expect(response.status).toBe(401);

      const data = await response.json();
      expect(data.error).toBe('Unauthorized');
    });
  });

  describe('POST /api/coach/tool', () => {
    it('returns 401 when not authenticated', async () => {
      (auth as any).mockResolvedValue({ userId: null });

      const { POST } = await import('../../coach/tool/route');
      const { NextRequest } = await import('next/server');
      const request = new NextRequest('http://localhost:3000/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'board_control', args: {} }),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(401);
      expect((await response.json()).error).toBe('Unauthorized');
    });

    it('returns 400 when the tool name is missing', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });

      const { POST } = await import('../../coach/tool/route');
      const { NextRequest } = await import('next/server');
      const request = new NextRequest('http://localhost:3000/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ args: {} }),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(400);
      expect((await response.json()).error).toBe('Missing tool name');
    });

    it('forwards to Hermes with the Clerk user id and returns the tool result', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });

      const hermesBody = { result: { ok: true }, board_actions: [] };
      const fetchMock = vi.fn(async () => ({
        ok: true,
        json: async () => hermesBody,
      }));
      global.fetch = fetchMock as any;

      const { POST } = await import('../../coach/tool/route');
      const { NextRequest } = await import('next/server');
      const request = new NextRequest('http://localhost:3000/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'board_control',
          args: { action_type: 'set_fen' },
          session_id: 'sess-1',
        }),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual(hermesBody);

      const [url, opts] = fetchMock.mock.calls[0] as any[];
      expect(url).toContain('/api/coach/tool/board_control');
      expect(opts.headers['X-User-Id']).toBe('user_123');
      expect(JSON.parse(opts.body)).toEqual({
        args: { action_type: 'set_fen' },
        session_id: 'sess-1',
      });
    });

    it('proxies check_moves through the bridge to Hermes', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });

      const hermesBody = { result: { legal_moves: ['e4'] }, board_actions: [] };
      const fetchMock = vi.fn(async () => ({ ok: true, json: async () => hermesBody }));
      global.fetch = fetchMock as any;

      const { POST } = await import('../../coach/tool/route');
      const { NextRequest } = await import('next/server');
      const request = new NextRequest('http://localhost:3000/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'check_moves',
          args: { fen: 'startpos', moves: ['Nf3'] },
        }),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(200);
      expect(await response.json()).toEqual(hermesBody);

      const [url] = fetchMock.mock.calls[0] as any[];
      expect(url).toContain('/api/coach/tool/check_moves');
    });

    it('surfaces a clear rate-limit error payload on Hermes 429', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });

      global.fetch = vi.fn(async () => ({
        ok: false,
        status: 429,
        json: async () => ({
          detail: {
            error: 'rate_limit_exceeded',
            message: 'Rate limit exceeded for free tier. Limit: 30 requests per minute.',
            retry_after: 12,
            tier: 'free',
          },
        }),
      })) as any;

      const { POST } = await import('../../coach/tool/route');
      const { NextRequest } = await import('next/server');
      const request = new NextRequest('http://localhost:3000/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'analyze_position', args: {} }),
      });

      const response = await POST(request as any);
      expect(response.status).toBe(429);
      const data = await response.json();
      // The voice hook reads data.error back to the model (coach says it's busy).
      expect(data.error).toContain('Rate limit exceeded');
      expect(data.rate_limited).toBe(true);
      expect(data.retry_after).toBe(12);
    });
  });
});
