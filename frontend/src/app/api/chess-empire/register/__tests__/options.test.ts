/**
 * Tests for GET /api/chess-empire/register/options — the JSON twin of the
 * /register branch picker. Same scripted Supabase mock as the page test:
 * newest-token-per-branch dedupe, online token, revoked/expired filtering,
 * and the apex (no org) empty state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const tokenScript: { current: ScriptedResponse } = { current: { data: [], error: null } };
const headerStore: { current: Record<string, string | null> } = {
  current: { 'x-org-id': 'org-1' },
};
const fromSpy = vi.fn();

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => {
      fromSpy(table);
      const chain: Record<string, unknown> = {
        select: () => chain,
        eq: () => Promise.resolve(tokenScript.current),
      };
      return chain;
    },
  },
}));

vi.mock('next/headers', () => ({
  headers: async () => ({
    get: (key: string) => headerStore.current[key] ?? null,
  }),
}));

import { GET } from '../options/route';

const iso = (d: string) => new Date(d).toISOString();
const row = (over: Record<string, unknown>) => ({
  token: 't',
  external_branch_id: 'b1',
  branch_name: 'Debut',
  kind: 'branch',
  expires_at: null,
  revoked_at: null,
  created_at: iso('2026-01-01'),
  ...over,
});

beforeEach(() => {
  tokenScript.current = { data: [], error: null };
  headerStore.current = { 'x-org-id': 'org-1' };
  fromSpy.mockClear();
});

describe('GET /api/chess-empire/register/options', () => {
  it('returns branches (newest token per branch) and the online option', async () => {
    tokenScript.current = {
      data: [
        row({ token: 'stale', created_at: iso('2026-01-01') }),
        row({ token: 'fresh', created_at: iso('2026-06-01') }),
        row({ token: 't-b2', external_branch_id: 'b2', branch_name: 'Almaty' }),
        row({ token: 't-online', external_branch_id: 'online', branch_name: 'Online', kind: 'online' }),
      ],
      error: null,
    };
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      branches: [
        { token: 'fresh', branchName: 'Debut' },
        { token: 't-b2', branchName: 'Almaty' },
      ],
      online: { token: 't-online', branchName: 'Online' },
    });
  });

  it('filters out revoked and expired tokens', async () => {
    tokenScript.current = {
      data: [
        row({ token: 'revoked', revoked_at: iso('2026-01-01') }),
        row({ token: 'expired', external_branch_id: 'b2', expires_at: iso('2020-01-01') }),
        row({ token: 'good', external_branch_id: 'b3', branch_name: 'Live' }),
      ],
      error: null,
    };
    expect(await (await GET()).json()).toEqual({
      branches: [{ token: 'good', branchName: 'Live' }],
      online: null,
    });
  });

  it('returns the empty state on a query error', async () => {
    tokenScript.current = { data: null, error: { message: 'boom' } };
    expect(await (await GET()).json()).toEqual({ branches: [], online: null });
  });

  it('never queries without an org (apex host)', async () => {
    headerStore.current = {};
    expect(await (await GET()).json()).toEqual({ branches: [], online: null });
    expect(fromSpy).not.toHaveBeenCalled();
  });
});
