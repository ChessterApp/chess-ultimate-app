import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

const clerk = vi.hoisted(() => ({
  userId: 'user_admin' as string | null,
  user: null as Record<string, unknown> | null,
  list: vi.fn(),
}));
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: clerk.userId }),
  currentUser: async () => clerk.user,
  clerkClient: async () => ({ users: { getUserList: clerk.list } }),
}));
vi.mock('server-only', () => ({}));

const db = vi.hoisted(() => ({
  tables: {} as Record<string, unknown[]>,
  missing: new Set<string>(),
}));

function query(table: string) {
  let columns = '';
  const q: Record<string, unknown> = {};
  const self = new Proxy(q, {
    get(_t, prop) {
      if (prop === 'select') return (cols: string) => ((columns = cols), self);
      if (prop === 'then') {
        const missing = [...db.missing].find((c) => columns.split(',').includes(c));
        const result = missing
          ? { data: null, error: { code: '42703', message: `column token_usage.${missing} does not exist` }, count: null }
          : { data: db.tables[table] ?? [], error: null, count: (db.tables[table] ?? []).length };
        return (resolve: (v: unknown) => void) => resolve(result);
      }
      return () => self;
    },
  });
  return self;
}
vi.mock('@/lib/supabase-admin', () => ({ supabaseAdmin: { from: (t: string) => query(t) } }));

import { GET } from '../route';

const req = (period = '7d') => new NextRequest(`https://chesster.io/api/admin/coach-usage?period=${period}`);

beforeEach(() => {
  clerk.userId = 'user_admin';
  clerk.user = { publicMetadata: { platform_role: 'super_admin' }, twoFactorEnabled: true };
  clerk.list.mockReset();
  clerk.list.mockResolvedValue({
    data: [{ id: 'user_a', firstName: 'Алия', lastName: 'С.', username: null, primaryEmailAddressId: 'e1',
      emailAddresses: [{ id: 'e1', emailAddress: 'aliya@example.com' }] }],
  });
  db.missing.clear();
  const now = new Date().toISOString();
  db.tables = {
    token_usage: [
      { user_id: 'user_a', surface: 'text', model: 'deepseek/deepseek-v4.1-flash', prompt_tokens: 100,
        completion_tokens: 20, estimated_cost_usd: 0.001, turn_id: 't1', created_at: now },
      { user_id: 'system', surface: 'playbook', model: 'm', prompt_tokens: 1, completion_tokens: 1,
        estimated_cost_usd: 0.01, created_at: now },
    ],
    voice_usage: [{ user_id: 'user_a', seconds: 60, last_heartbeat_at: now }],
    organization_members: [{ user_id: 'user_a', organization_id: 'o1', name: null, email: null }],
    organizations: [{ id: 'o1', name: 'Chess Empire' }],
  };
});

describe('GET /api/admin/coach-usage', () => {
  it('is for signed-in platform super-admins with 2FA only', async () => {
    clerk.userId = null;
    expect((await GET(req())).status).toBe(401);
    clerk.userId = 'user_x';
    clerk.user = { publicMetadata: {}, twoFactorEnabled: true };
    expect((await GET(req())).status).toBe(403);
    clerk.user = { publicMetadata: { platform_role: 'super_admin' }, twoFactorEnabled: false };
    expect((await GET(req())).status).toBe(403);
  });

  it('returns each student with name, school, spend and voice minutes', async () => {
    const res = await GET(req('today'));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.period.name).toBe('today');
    expect(body.students).toHaveLength(1);
    expect(body.students[0]).toMatchObject({
      userId: 'user_a', name: 'Алия С.', email: 'aliya@example.com', schools: ['Chess Empire'],
      questions: 1, voiceMinutes: 1, costUsd: 0.001,
    });
    expect(body.service).toEqual({ calls: 1, costUsd: 0.01 });
  });

  it('falls back to the older columns when a migration is missing', async () => {
    db.missing.add('turn_id');
    const body = await (await GET(req())).json();
    expect(body.students[0].costUsd).toBe(0.001);
  });

  it('still answers when Clerk is down (names from the school roster)', async () => {
    clerk.list.mockRejectedValue(new Error('clerk down'));
    db.tables.organization_members = [{ user_id: 'user_a', organization_id: 'o1', name: 'Алия', email: 'a@x.kz' }];
    const body = await (await GET(req())).json();
    expect(body.students[0]).toMatchObject({ name: 'Алия', email: 'a@x.kz' });
  });
});
