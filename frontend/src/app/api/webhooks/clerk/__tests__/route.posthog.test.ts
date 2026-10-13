/**
 * Clerk webhook → PostHog wiring (tracking plan T1):
 *   - user.created → server-side `user_signed_up` (method enum, no PII,
 *     $set_once signup_date).
 *   - user.deleted → PostHog person lookup + delete (F11). Real
 *     `deletePostHogPerson` with fetch mocked; the webhook must return 200 and
 *     keep running the existing cascade whatever PostHog does.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const deletes: string[] = [];

function makeBuilder(table: string) {
  let mode: 'select' | 'delete' = 'select';
  const chain: Record<string, unknown> = {
    select: () => chain,
    delete: () => {
      mode = 'delete';
      return chain;
    },
    eq: () => chain,
    in: () => chain,
    limit: () => chain,
    then(onFulfilled: (v: unknown) => unknown, onRejected?: (e: unknown) => unknown) {
      if (mode === 'delete') deletes.push(table);
      return Promise.resolve({ data: [], error: null }).then(onFulfilled, onRejected);
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: { from: (table: string) => makeBuilder(table) },
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
    get: (name: string) =>
      ({ 'svix-id': 'msg_1', 'svix-timestamp': '1', 'svix-signature': 'v1,x' })[name] ?? null,
  }),
}));

vi.mock('@clerk/nextjs/server', () => ({ clerkClient: async () => ({}) }));
vi.mock('@/lib/chess-empire-member', () => ({ getMembershipStateForUser: vi.fn() }));
vi.mock('@/lib/chess-empire-client', () => ({ findCoachesByEmail: vi.fn() }));
vi.mock('@/lib/chess-empire-jwt-link', () => ({
  logLinkAttempt: vi.fn(),
  upsertMemberLink: vi.fn(),
  linkMemberViaInviteJwt: vi.fn(),
}));
const blocklistSubscriber = vi.fn();
vi.mock('@/lib/listmonk', () => ({
  createSubscriber: vi.fn(async () => ({ id: 1, created: true })),
  blocklistSubscriber: (...a: unknown[]) => blocklistSubscriber(...a),
  LISTS: { ALL_USERS: 3, WELCOME_SEQUENCE: 4 },
}));

const captureServer = vi.fn();
vi.mock('@/lib/analytics/server', () => ({
  captureServer: (...a: unknown[]) => captureServer(...a),
}));

import { POST } from '../route';

const fetchMock = vi.fn();

function post(event: unknown) {
  return POST(
    new Request('http://localhost/api/webhooks/clerk', {
      method: 'POST',
      body: JSON.stringify(event),
    }),
  );
}

function deleted(id = 'user_del') {
  return { type: 'user.deleted', data: { id, email_addresses: [{ email_address: 'g@x.io' }] } };
}

beforeEach(() => {
  process.env.CLERK_WEBHOOK_SECRET = 'whsec_test';
  deletes.length = 0;
  captureServer.mockReset();
  blocklistSubscriber.mockReset();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  vi.stubEnv('POSTHOG_PERSONAL_API_KEY', 'phx_test');
  vi.stubEnv('POSTHOG_PROJECT_ID', '7');
  vi.stubEnv('POSTHOG_API_HOST', '');
  for (const m of ['log', 'info', 'warn', 'error'] as const) {
    vi.spyOn(console, m).mockImplementation(() => {});
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});

describe('user.created → user_signed_up', () => {
  it('captures a server-side signup with method enum + signup_date, no PII', async () => {
    const res = await post({
      type: 'user.created',
      data: {
        id: 'user_new',
        email_addresses: [{ id: 'e1', email_address: 'parent@example.com' }],
        primary_email_address_id: 'e1',
        first_name: 'Ann',
        external_accounts: [{ provider: 'oauth_google' }],
        created_at: Date.UTC(2026, 9, 13, 8),
      },
    });
    expect(res.status).toBe(200);
    expect(captureServer).toHaveBeenCalledWith('user_new', 'user_signed_up', {
      method: 'google',
      signup_source: 'server',
      $set_once: { signup_date: '2026-10-13' },
    });
    expect(JSON.stringify(captureServer.mock.calls)).not.toMatch(/parent@example|Ann/);
  });

  it('derives email / phone methods', async () => {
    await post({
      type: 'user.created',
      data: { id: 'u1', email_addresses: [{ id: 'e', email_address: 'a@b.c' }] },
    });
    await post({ type: 'user.created', data: { id: 'u2', phone_numbers: [{ id: 'p' }] } });
    expect(captureServer.mock.calls[0][2]).toMatchObject({ method: 'email' });
    expect(captureServer.mock.calls[1][2]).toMatchObject({ method: 'phone' });
  });
});

describe('user.deleted → PostHog person delete', () => {
  it('found → DELETE called, cascade still runs', async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ results: [{ uuid: 'p-uuid' }] })))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const res = await post(deleted());
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1][0]).toBe(
      'https://us.posthog.com/api/projects/7/persons/p-uuid/?delete_events=true',
    );
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ method: 'DELETE' });
    expect(blocklistSubscriber).toHaveBeenCalledWith('g@x.io');
    expect(deletes).toContain('coach_sessions');
  });

  it('not found → no DELETE', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ results: [] })));
    const res = await post(deleted());
    expect(res.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('env missing → skipped, webhook succeeds', async () => {
    vi.stubEnv('POSTHOG_PROJECT_ID', '');
    const res = await post(deleted());
    expect(res.status).toBe(200);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(deletes).toContain('subscriptions');
  });

  it('API error → webhook still returns success', async () => {
    fetchMock.mockResolvedValueOnce(new Response('boom', { status: 500 }));
    const res = await post(deleted());
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ received: true });
    expect(deletes).toContain('coach_sessions');
  });
});
