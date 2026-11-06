/**
 * Tests for GET /api/chess-empire/welcome/[branchToken] — the public JSON twin
 * of the /welcome/<token> header. Covers: valid branch and online tokens,
 * missing / revoked / expired → 404, no org or external ids in the payload,
 * and the 30/min per-IP rate limit.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const tokenScript: { current: ScriptedResponse } = { current: { data: null, error: null } };

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain: Record<string, unknown> = {
        select: () => chain,
        eq: () => chain,
        maybeSingle: () => Promise.resolve(tokenScript.current),
      };
      return chain;
    },
  },
}));

import { GET } from '../[branchToken]/route';
import { _resetRateLimitForTests } from '@/lib/in-memory-rate-limit';

const iso = (d: string) => new Date(d).toISOString();
const row = (over: Record<string, unknown> = {}) => ({
  organization_id: 'org-secret',
  external_branch_id: 'ext-branch-secret',
  branch_name: 'Debut',
  kind: 'branch',
  expires_at: null,
  revoked_at: null,
  ...over,
});

function call(token: string, ip = '1.2.3.4') {
  const req = new NextRequest(`https://chess-empire.chesster.io/api/chess-empire/welcome/${token}`, {
    headers: { 'x-forwarded-for': ip },
  });
  return GET(req, { params: Promise.resolve({ branchToken: token }) });
}

beforeEach(() => {
  tokenScript.current = { data: null, error: null };
  _resetRateLimitForTests();
});

describe('GET /api/chess-empire/welcome/[branchToken]', () => {
  it('returns branchName and kind for a valid branch token, without ids', async () => {
    tokenScript.current = { data: row(), error: null };
    const res = await call('tok');
    expect(res.status).toBe(200);
    const json = await res.json();
    expect(json).toEqual({ branchName: 'Debut', kind: 'branch' });
    expect(JSON.stringify(json)).not.toContain('secret');
  });

  it('reports kind online for an online token', async () => {
    tokenScript.current = { data: row({ kind: 'online', branch_name: 'Online' }), error: null };
    expect(await (await call('tok')).json()).toEqual({ branchName: 'Online', kind: 'online' });
  });

  it.each([
    ['unknown', { data: null, error: null }],
    ['query error', { data: null, error: { message: 'boom' } }],
    ['revoked', { data: row({ revoked_at: iso('2026-01-01') }), error: null }],
    ['expired', { data: row({ expires_at: iso('2020-01-01') }), error: null }],
  ])('404 invalid_token for a %s token', async (_label, script) => {
    tokenScript.current = script;
    const res = await call('tok');
    expect(res.status).toBe(404);
    expect(await res.json()).toEqual({ error: 'invalid_token' });
  });

  it('rate-limits at 30 requests per minute per IP', async () => {
    tokenScript.current = { data: row(), error: null };
    for (let i = 0; i < 30; i++) {
      expect((await call('tok', '9.9.9.9')).status).toBe(200);
    }
    const limited = await call('tok', '9.9.9.9');
    expect(limited.status).toBe(429);
    expect(limited.headers.get('Retry-After')).toBeTruthy();
    // A different IP is unaffected.
    expect((await call('tok', '8.8.8.8')).status).toBe(200);
  });
});
