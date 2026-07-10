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
});
