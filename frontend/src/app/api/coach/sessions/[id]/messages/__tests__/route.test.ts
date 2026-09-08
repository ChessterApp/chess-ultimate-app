import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

import { auth } from '@clerk/nextjs/server';

const makeParams = (id: string) => ({ params: Promise.resolve({ id }) });

describe('/api/coach/sessions/[id]/messages proxy', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = originalFetch;
  });

  describe('GET', () => {
    it('returns 401 when not authenticated', async () => {
      (auth as any).mockResolvedValue({ userId: null });
      const { GET } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/s1/messages',
      );
      const res = await GET(req, makeParams('s1'));
      expect(res.status).toBe(401);
    });

    it('forwards to Hermes with the user id header and limit query', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ messages: [{ role: 'user', content: 'hi' }] }),
      });
      global.fetch = fetchSpy as any;

      const { GET } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/s1/messages?limit=20',
      );
      const res = await GET(req, makeParams('s1'));

      expect(res.status).toBe(200);
      const data = await res.json();
      expect(data.messages).toHaveLength(1);

      const [url, opts] = fetchSpy.mock.calls[0];
      expect(url).toContain('/api/coach/sessions/s1/messages');
      expect(url).toContain('limit=20');
      expect(opts.headers['X-User-Id']).toBe('user_123');
    });

    it('propagates a Hermes 404', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });
      global.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as any;

      const { GET } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/nope/messages',
      );
      const res = await GET(req, makeParams('nope'));
      expect(res.status).toBe(404);
    });
  });

  describe('POST', () => {
    it('returns 401 when not authenticated', async () => {
      (auth as any).mockResolvedValue({ userId: null });
      const { POST } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/s1/messages',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'user', content: 'hi' }),
        },
      );
      const res = await POST(req, makeParams('s1'));
      expect(res.status).toBe(401);
    });

    it('returns 400 when role or content is missing', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });
      const { POST } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/s1/messages',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ role: 'user' }),
        },
      );
      const res = await POST(req, makeParams('s1'));
      expect(res.status).toBe(400);
    });

    it('forwards role, content and source to Hermes', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, message_count: 1 }),
      });
      global.fetch = fetchSpy as any;

      const { POST } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/s1/messages',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            role: 'assistant',
            content: 'spoken reply',
            source: 'voice',
          }),
        },
      );
      const res = await POST(req, makeParams('s1'));

      expect(res.status).toBe(200);
      const [url, opts] = fetchSpy.mock.calls[0];
      expect(url).toContain('/api/coach/sessions/s1/messages');
      expect(opts.method).toBe('POST');
      expect(opts.headers['X-User-Id']).toBe('user_123');
      const sent = JSON.parse(opts.body);
      expect(sent).toEqual({
        role: 'assistant',
        content: 'spoken reply',
        source: 'voice',
      });
    });

    it('forwards client_ts and turn_id for voice write-back (Phase 2)', async () => {
      (auth as any).mockResolvedValue({ userId: 'user_123' });
      const fetchSpy = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ ok: true, message_count: 1 }),
      });
      global.fetch = fetchSpy as any;

      const { POST } = await import('../route');
      const { NextRequest } = await import('next/server');
      const req = new NextRequest(
        'http://localhost:3000/api/coach/sessions/s1/messages',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            role: 'user',
            content: 'spoken hello',
            source: 'voice',
            client_ts: '2026-09-08T12:00:00.000Z',
            turn_id: 't-voice-1',
          }),
        },
      );
      const res = await POST(req, makeParams('s1'));

      expect(res.status).toBe(200);
      const sent = JSON.parse(fetchSpy.mock.calls[0][1].body);
      expect(sent.client_ts).toBe('2026-09-08T12:00:00.000Z');
      expect(sent.turn_id).toBe('t-voice-1');
    });
  });
});
