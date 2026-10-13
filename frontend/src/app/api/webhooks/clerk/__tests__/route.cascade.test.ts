/**
 * Tests for the Clerk `user.deleted` account-deletion cascade (P1).
 *
 * On `user.deleted` the webhook deletes all of the user's data with ONE call to
 * the `delete_user_data` RPC (migration 053, single transaction):
 *   - rpc called with the Clerk id; success → 200.
 *   - rpc error → 500, so Svix retries the delivery.
 *   - DB deletion runs before the best-effort PostHog delete.
 *   - a replay (zero-row counts) still returns 200.
 *   - no user id → no rpc.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const calls: string[] = [];
const rpc = vi.fn();

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => {
      throw new Error(`unexpected supabaseAdmin.from(${table})`);
    },
    rpc: (...args: unknown[]) => {
      calls.push('rpc');
      return rpc(...args);
    },
  },
}));

vi.mock('svix', () => ({
  Webhook: class {
    verify(body: string) {
      return JSON.parse(body);
    }
  },
}));

vi.mock('next/headers', () => ({
  headers: async () => ({
    get(name: string) {
      const map: Record<string, string> = {
        'svix-id': 'msg_test_user_deleted',
        'svix-timestamp': String(Math.floor(Date.now() / 1000)),
        'svix-signature': 'v1,dummy',
      };
      return map[name] ?? null;
    },
  }),
}));

vi.mock('@clerk/nextjs/server', () => ({
  clerkClient: async () => ({}),
}));

vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipStateForUser: vi.fn(),
}));

const deletePostHogPerson = vi.fn();
vi.mock('@/lib/analytics/person-delete', () => ({
  deletePostHogPerson: (...args: unknown[]) => {
    calls.push('posthog');
    return deletePostHogPerson(...args);
  },
}));

vi.mock('@/lib/chess-empire-client', () => ({
  findCoachesByEmail: vi.fn(),
}));

import { POST } from '../route';

function makeRequest(event: unknown): Request {
  return new Request('http://localhost/api/webhooks/clerk', {
    method: 'POST',
    body: JSON.stringify(event),
    headers: { 'content-type': 'application/json' },
  });
}

function deletedEvent(id: string | undefined): unknown {
  return { type: 'user.deleted', data: { id } };
}

beforeEach(() => {
  process.env.CLERK_WEBHOOK_SECRET = 'whsec_test';
  calls.length = 0;
  rpc.mockReset();
  rpc.mockResolvedValue({ data: { coach_sessions: 2, user_games: 5 }, error: null });
  deletePostHogPerson.mockReset();
});

describe('POST /api/webhooks/clerk — user.deleted cascade', () => {
  it('calls delete_user_data with the Clerk id and returns 200', async () => {
    const res = await POST(makeRequest(deletedEvent('user_del_1')));
    expect(res.status).toBe(200);
    expect(rpc).toHaveBeenCalledTimes(1);
    expect(rpc).toHaveBeenCalledWith('delete_user_data', { p_clerk_id: 'user_del_1' });
    expect(deletePostHogPerson).toHaveBeenCalledWith('user_del_1');
  });

  it('deletes DB data before the best-effort PostHog call', async () => {
    await POST(makeRequest(deletedEvent('user_del_2')));
    expect(calls).toEqual(['rpc', 'posthog']);
  });

  it('rpc error → 500 so Svix retries; best-effort steps are not reached', async () => {
    rpc.mockResolvedValue({ data: null, error: { message: 'deadlock detected' } });
    const res = await POST(makeRequest(deletedEvent('user_del_3')));
    expect(res.status).toBe(500);
    expect(deletePostHogPerson).not.toHaveBeenCalled();
  });

  it('rpc rejection → 500', async () => {
    rpc.mockRejectedValue(new Error('network down'));
    const res = await POST(makeRequest(deletedEvent('user_del_4')));
    expect(res.status).toBe(500);
  });

  it('replay with zero-row counts is idempotent → 200', async () => {
    rpc.mockResolvedValue({ data: { coach_sessions: 0, user_games: 0 }, error: null });
    const first = await POST(makeRequest(deletedEvent('user_del_5')));
    const replay = await POST(makeRequest(deletedEvent('user_del_5')));
    expect(first.status).toBe(200);
    expect(replay.status).toBe(200);
    expect(rpc).toHaveBeenCalledTimes(2);
  });

  it('no user id → no rpc, still 200', async () => {
    const res = await POST(makeRequest(deletedEvent(undefined)));
    expect(res.status).toBe(200);
    expect(rpc).not.toHaveBeenCalled();
    expect(deletePostHogPerson).not.toHaveBeenCalled();
  });
});
