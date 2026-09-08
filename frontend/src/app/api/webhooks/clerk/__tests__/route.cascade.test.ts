/**
 * Tests for the Clerk `user.deleted` coach-data cascade (Phase 3, Task 3).
 *
 * On `user.deleted` the webhook must best-effort delete the user's coach data
 * across every telemetry / conversation table:
 *   - coach_messages (via the user's coach_sessions ids — no user_id column)
 *   - coach_sessions (by user_id)
 *   - coach_events, token_usage, voice_usage, analytics_events (by user_id)
 * One table's failure must not abort the rest, and the webhook still returns 200.
 *
 * This file carries its own Supabase mock (supporting select + delete + eq + in)
 * so it stays independent of the user.created suite's select/limit-only mock.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

type Delete = { table: string; filters: Array<[string, unknown]>; inFilter: [string, unknown[]] | null };

const state: {
  sessions: Array<{ id: string }>;
  deletes: Delete[];
  fromCalls: string[];
  selectError: { message: string } | null;
  deleteErrors: Record<string, { message: string } | null>;
} = {
  sessions: [],
  deletes: [],
  fromCalls: [],
  selectError: null,
  deleteErrors: {},
};

function resetState(overrides: Partial<typeof state> = {}) {
  state.sessions = overrides.sessions ?? [];
  state.deletes = [];
  state.fromCalls = [];
  state.selectError = overrides.selectError ?? null;
  state.deleteErrors = overrides.deleteErrors ?? {};
}

function makeBuilder(table: string) {
  const rec = {
    mode: 'select' as 'select' | 'delete',
    filters: [] as Array<[string, unknown]>,
    inFilter: null as [string, unknown[]] | null,
  };
  const resolve = () => {
    if (rec.mode === 'select') {
      if (table === 'coach_sessions') {
        return { data: state.sessions, error: state.selectError };
      }
      return { data: [], error: null };
    }
    // delete
    state.deletes.push({ table, filters: rec.filters, inFilter: rec.inFilter });
    return { data: null, error: state.deleteErrors[table] ?? null };
  };
  const chain: Record<string, unknown> = {
    select(_cols: string) {
      rec.mode = 'select';
      return chain;
    },
    delete() {
      rec.mode = 'delete';
      return chain;
    },
    eq(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    in(col: string, vals: unknown[]) {
      rec.inFilter = [col, vals];
      return chain;
    },
    then(onFulfilled: (v: unknown) => unknown, onRejected?: (e: unknown) => unknown) {
      return Promise.resolve(resolve()).then(onFulfilled, onRejected);
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => {
      state.fromCalls.push(table);
      return makeBuilder(table);
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

const blocklistSubscriber = vi.fn();
vi.mock('@/lib/listmonk', () => ({
  createSubscriber: vi.fn(),
  blocklistSubscriber: (...args: unknown[]) => blocklistSubscriber(...args),
  LISTS: { ALL_USERS: 3, WELCOME_SEQUENCE: 4 },
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

function deletedEvent(id: string | undefined, email = 'gone@example.com'): unknown {
  return {
    type: 'user.deleted',
    data: {
      id,
      email_addresses: email ? [{ email_address: email }] : [],
    },
  };
}

beforeEach(() => {
  process.env.CLERK_WEBHOOK_SECRET = 'whsec_test';
  blocklistSubscriber.mockReset();
  resetState();
});

function deletesFor(table: string) {
  return state.deletes.filter((d) => d.table === table);
}

describe('POST /api/webhooks/clerk — user.deleted cascade', () => {
  it('cascades across every user-scoped coach table and deletes messages via sessions', async () => {
    resetState({ sessions: [{ id: 's1' }, { id: 's2' }] });

    const res = await POST(makeRequest(deletedEvent('user_del_1')));
    expect(res.status).toBe(200);

    // Blocklist still runs.
    expect(blocklistSubscriber).toHaveBeenCalledWith('gone@example.com');

    // coach_messages deleted via the user's session ids.
    const msgDeletes = deletesFor('coach_messages');
    expect(msgDeletes).toHaveLength(1);
    expect(msgDeletes[0].inFilter).toEqual(['session_id', ['s1', 's2']]);

    // coach_sessions + the four user_id-keyed tables each deleted by user_id.
    for (const table of [
      'coach_sessions',
      'coach_events',
      'token_usage',
      'voice_usage',
      'analytics_events',
    ]) {
      const dels = deletesFor(table);
      expect(dels, `expected a delete on ${table}`).toHaveLength(1);
      expect(dels[0].filters).toContainEqual(['user_id', 'user_del_1']);
    }
  });

  it('skips coach_messages delete when the user has no sessions', async () => {
    resetState({ sessions: [] });

    const res = await POST(makeRequest(deletedEvent('user_del_2')));
    expect(res.status).toBe(200);

    expect(deletesFor('coach_messages')).toHaveLength(0);
    // Other tables still purged.
    expect(deletesFor('coach_events')).toHaveLength(1);
  });

  it('one table failure does not abort the rest (best-effort)', async () => {
    resetState({
      sessions: [{ id: 's1' }],
      deleteErrors: { coach_events: { message: 'boom' } },
    });

    const res = await POST(makeRequest(deletedEvent('user_del_3')));
    expect(res.status).toBe(200);

    // The failing table was attempted, and later tables still ran.
    expect(deletesFor('coach_events')).toHaveLength(1);
    expect(deletesFor('token_usage')).toHaveLength(1);
    expect(deletesFor('voice_usage')).toHaveLength(1);
    expect(deletesFor('analytics_events')).toHaveLength(1);
  });

  it('a thrown session lookup does not block the user_id-keyed purges', async () => {
    resetState({
      sessions: [],
      selectError: { message: 'select down' },
    });

    const res = await POST(makeRequest(deletedEvent('user_del_4')));
    expect(res.status).toBe(200);

    // coach_messages skipped (lookup failed) but the rest still purge.
    expect(deletesFor('coach_messages')).toHaveLength(0);
    expect(deletesFor('coach_events')).toHaveLength(1);
    expect(deletesFor('analytics_events')).toHaveLength(1);
  });

  it('no user id → cascade skipped, still 200', async () => {
    resetState();
    const res = await POST(makeRequest(deletedEvent(undefined)));
    expect(res.status).toBe(200);
    expect(state.deletes).toHaveLength(0);
  });
});
