import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ getAuth: vi.fn() }));

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { getAuth } from '@clerk/nextjs/server';
import { _resetRateLimitForTests } from '@/lib/rate-limit-core';
import { checkVisionRateLimit, clientIp } from '@/lib/vision-rate-limit';

// The photo and scoresheet proxies are Pages Router routes: anything they load
// must not import 'server-only' (it throws there — every request was a 500
// from 2026-09-21 to 2026-10-06). Vitest aliases the package, so only the
// sources can tell.
describe('vision proxies load without server-only', () => {
  const src = (p: string) => readFileSync(join(__dirname, '..', '..', p), 'utf8');
  it.each([
    'lib/vision-rate-limit.ts',
    'lib/rate-limit-core.ts',
    'pages/api/convert-image.ts',
    'pages/api/convert-scoresheet.ts',
  ])('%s', (file) => {
    const text = src(file);
    expect(text).not.toMatch(/^\s*import\s+['"]server-only['"]/m);
    expect(text).not.toMatch(/^\s*import[^\n]*from\s+['"]@\/lib\/in-memory-rate-limit['"]/m);
  });
});

const req = (headers: Record<string, string> = {}) =>
  ({ headers, socket: { remoteAddress: '10.0.0.1' } }) as any;

const LIMITS = { perUser: 3, perIp: 2, windowMs: 60_000 };

describe('vision rate limit', () => {
  beforeEach(() => {
    _resetRateLimitForTests();
    vi.mocked(getAuth).mockReturnValue({ userId: null } as any);
  });

  it('charges anonymous callers per IP with the tighter budget', () => {
    const r = req({ 'x-forwarded-for': '203.0.113.7, 10.0.0.2' });
    expect(checkVisionRateLimit(r, 'img', LIMITS).allowed).toBe(true);
    expect(checkVisionRateLimit(r, 'img', LIMITS).allowed).toBe(true);
    const third = checkVisionRateLimit(r, 'img', LIMITS);
    expect(third.allowed).toBe(false);
    expect(third.retryAfterSeconds).toBeGreaterThan(0);
    expect(third.subject).toBe('vision:img:ip:203.0.113.7');
  });

  it('charges signed-in callers per user with the larger budget', () => {
    vi.mocked(getAuth).mockReturnValue({ userId: 'user_1' } as any);
    const r = req({ 'x-forwarded-for': '203.0.113.7' });
    for (let i = 0; i < 3; i++) expect(checkVisionRateLimit(r, 'img', LIMITS).allowed).toBe(true);
    const fourth = checkVisionRateLimit(r, 'img', LIMITS);
    expect(fourth.allowed).toBe(false);
    expect(fourth.subject).toBe('vision:img:user:user_1');
  });

  it('keeps separate budgets per proxy name and per IP', () => {
    const a = req({ 'x-forwarded-for': '198.51.100.1' });
    const b = req({ 'x-forwarded-for': '198.51.100.2' });
    checkVisionRateLimit(a, 'img', LIMITS);
    checkVisionRateLimit(a, 'img', LIMITS);
    expect(checkVisionRateLimit(a, 'img', LIMITS).allowed).toBe(false);
    expect(checkVisionRateLimit(a, 'sheet', LIMITS).allowed).toBe(true);
    expect(checkVisionRateLimit(b, 'img', LIMITS).allowed).toBe(true);
  });

  it('falls back to x-real-ip, then the socket address', () => {
    expect(clientIp(req({ 'x-real-ip': '192.0.2.9' }))).toBe('192.0.2.9');
    expect(clientIp(req())).toBe('10.0.0.1');
  });
});
