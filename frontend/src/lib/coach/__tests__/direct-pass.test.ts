import { describe, it, expect, vi, afterEach } from 'vitest';

vi.mock('server-only', () => ({}));

import { mintDirectPass, signDirectPass, DIRECT_PASS_TTL_S } from '../direct-pass';

// The same pass hermes/tests/unit/test_direct_access_1123.py checks: a pass this site signs is one Hermes takes.
const VECTOR = 'v1.eyJzdWIiOiJ1c2VyX3ZlY3RvciIsInRpZXIiOiJwcmVtaXVtIiwiZXhwIjoxNzk1NDMwMDAwLCJhdWQiOiJjb2FjaC1kaXJlY3QifQ.FaWCHfhP0mTe9xhUSAt9z3voO-wAoAgH5fJznOkoGbg';

describe('the direct path pass (23.11)', () => {
  afterEach(() => vi.unstubAllEnvs());

  it('signs exactly as Hermes checks', () => {
    expect(signDirectPass({ sub: 'user_vector', tier: 'premium', exp: 1795430000, aud: 'coach-direct' }, 'vector-secret')).toBe(VECTOR);
  });

  it('is off without the address or the secret', () => {
    vi.stubEnv('COACH_DIRECT_URL', '');
    vi.stubEnv('COACH_DIRECT_SECRET', 's');
    expect(mintDirectPass('user_a', 'free')).toBeNull();
    vi.stubEnv('COACH_DIRECT_URL', 'https://coach-api.chesster.io');
    vi.stubEnv('COACH_DIRECT_SECRET', '');
    expect(mintDirectPass('user_a', 'free')).toBeNull();
  });

  it('names the student, the plan and a short expiry', () => {
    vi.stubEnv('COACH_DIRECT_URL', 'https://coach-api.chesster.io/');
    vi.stubEnv('COACH_DIRECT_SECRET', 'vector-secret');
    const now = 1_795_429_700_000;
    const pass = mintDirectPass('user_vector', 'premium', now)!;
    expect(pass.url).toBe('https://coach-api.chesster.io');
    expect(pass.expiresAt).toBe(now + DIRECT_PASS_TTL_S * 1000);
    expect(pass.token).toBe(VECTOR);
  });
});
