import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('next/server', async (importOriginal) => ({
  ...(await importOriginal<typeof import('next/server')>()),
  after: (fn: () => unknown) => fn(),
}));
const authMock = vi.fn();
vi.mock('@clerk/nextjs/server', () => ({ auth: () => authMock() }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'free' }));
const captureServer = vi.fn();
vi.mock('@/lib/analytics/server', () => ({
  captureServer: (...a: unknown[]) => captureServer(...a),
}));

import { NextRequest } from 'next/server';
import { POST } from '../route';

function req(body: unknown) {
  return new NextRequest('http://localhost/api/coach/chat', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

describe('POST /api/coach/chat — coach_message_sent', () => {
  beforeEach(() => {
    captureServer.mockReset();
    authMock.mockResolvedValue({ userId: 'user_c' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 500 })));
  });

  afterEach(() => vi.unstubAllGlobals());

  it('captures the message server-side without its content', async () => {
    const res = await POST(req({ message: 'what is a fork?', fen: '8/8/8/8/8/8/8/8 w - - 0 1' }));
    await res.text();
    expect(captureServer).toHaveBeenCalledWith('user_c', 'coach_message_sent', {
      surface: 'coach',
      plan: 'free',
    });
    expect(JSON.stringify(captureServer.mock.calls)).not.toContain('fork');
  });

  it('does not capture invalid requests', async () => {
    const res = await POST(req({}));
    expect(res.status).toBe(400);
    expect(captureServer).not.toHaveBeenCalled();
  });
});
