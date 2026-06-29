import { describe, it, expect, vi, beforeEach } from 'vitest';

// Clerk auth mock
vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

// Supabase admin mock — table-driven builder so we can script per-table
// responses for each test (lookup → update → upsert → update).
interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

interface Recorded {
  table: string;
  op: string;
  payload?: unknown;
  filters: Array<[string, unknown]>;
}

const recorded: Recorded[] = [];
const scripts: Record<string, ScriptedResponse[]> = {};

function nextScript(table: string, op: string): ScriptedResponse {
  const key = `${table}.${op}`;
  const queue = scripts[key];
  if (!queue || queue.length === 0) {
    return { data: null, error: null };
  }
  return queue.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const rec: Recorded = { table, op: '', filters: [] };
  let pushed = false;
  const finalize = (op: string) => {
    rec.op = op;
    const resp = nextScript(table, op);
    if (!pushed) {
      recorded.push(rec);
      pushed = true;
    }
    return Promise.resolve(resp);
  };
  const chain: Record<string, unknown> = {
    select(_cols?: string) {
      rec.op = rec.op || 'select';
      return chain;
    },
    eq(col: string, val: unknown) {
      rec.filters.push([col, val]);
      return chain;
    },
    maybeSingle() {
      return finalize(rec.op || 'select');
    },
    single() {
      return finalize(rec.op || 'select');
    },
    update(payload: unknown) {
      rec.op = 'update';
      rec.payload = payload;
      return chain;
    },
    upsert(payload: unknown, _opts?: unknown) {
      rec.op = 'upsert';
      rec.payload = payload;
      if (!pushed) {
        recorded.push(rec);
        pushed = true;
      }
      return Promise.resolve(nextScript(table, 'upsert'));
    },
    // PromiseLike: enables `await supabase.from(...).update(...).eq(...)`
    then(onFulfilled: (v: ScriptedResponse) => unknown, onRejected?: (e: unknown) => unknown) {
      return finalize(rec.op || 'select').then(onFulfilled, onRejected);
    },
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => makeBuilder(table),
  },
}));

import { auth } from '@clerk/nextjs/server';

function mockAuth(userId: string | null) {
  (auth as unknown as { mockResolvedValue: (v: unknown) => void }).mockResolvedValue({
    userId,
  });
}

function jsonReq(body: unknown): Request {
  return new Request('http://localhost/api/promo/redeem', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

function resetMocks() {
  recorded.length = 0;
  for (const k of Object.keys(scripts)) delete scripts[k];
  vi.clearAllMocks();
}

const ORG = '00000000-0000-0000-0000-000000000001';
const USER = 'user_owner_1';

function scriptOwner() {
  scripts['organization_members.select'] = [
    { data: { role: 'owner' }, error: null },
  ];
}

function scriptPromo(promo: Record<string, unknown> | null) {
  scripts['promo_codes.select'] = [{ data: promo, error: null }];
}

describe('POST /api/promo/redeem', () => {
  beforeEach(() => resetMocks());

  it('returns 401 when not authenticated', async () => {
    mockAuth(null);
    const { POST } = await import('../route');
    const res = await POST(jsonReq({}) as never);
    expect(res.status).toBe(401);
  });

  it('returns 400 on bad JSON', async () => {
    mockAuth(USER);
    const { POST } = await import('../route');
    const bad = new Request('http://localhost/api/promo/redeem', {
      method: 'POST',
      body: '}{not json',
    });
    const res = await POST(bad as never);
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('bad_json');
  });

  it('returns 400 when required fields missing', async () => {
    mockAuth(USER);
    const { POST } = await import('../route');
    const res = await POST(jsonReq({ code: 'FREE' }) as never);
    expect(res.status).toBe(400);
  });

  it('returns 400 for invalid tier', async () => {
    mockAuth(USER);
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'bogus', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_tier');
  });

  it('returns 400 for invalid cycle', async () => {
    mockAuth(USER);
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'forever' }) as never,
    );
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('invalid_cycle');
  });

  it('returns 403 when caller is not an owner', async () => {
    mockAuth(USER);
    scripts['organization_members.select'] = [
      { data: { role: 'teacher' }, error: null },
    ];
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(403);
  });

  it('returns 403 when caller is not even a member', async () => {
    mockAuth(USER);
    scripts['organization_members.select'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(403);
  });

  it('returns 404 when code does not exist', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo(null);
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'NOPE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(404);
    expect((await res.json()).error).toBe('not_found');
  });

  it('returns 410 for inactive code', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'OLD',
      discount_pct: 100,
      max_uses: null,
      uses: 0,
      active: false,
      expires_at: null,
    });
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'OLD', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(410);
    expect((await res.json()).error).toBe('inactive');
  });

  it('returns 410 for expired code', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'EXP',
      discount_pct: 100,
      max_uses: null,
      uses: 0,
      active: true,
      expires_at: '2020-01-01T00:00:00Z',
    });
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'EXP', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(410);
    expect((await res.json()).error).toBe('expired');
  });

  it('returns 409 when uses already at max_uses', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'CAP',
      discount_pct: 100,
      max_uses: 5,
      uses: 5,
      active: true,
      expires_at: null,
    });
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'CAP', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(409);
    expect((await res.json()).error).toBe('code_exhausted');
  });

  it('rejects partial-discount codes with 400 partial_discount_unsupported', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'HALF',
      discount_pct: 50,
      max_uses: null,
      uses: 0,
      active: true,
      expires_at: null,
    });
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'HALF', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(400);
    expect((await res.json()).error).toBe('partial_discount_unsupported');
  });

  it('returns 409 if CAS update loses the race (returns no row)', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'FREE',
      discount_pct: 100,
      max_uses: 1,
      uses: 0,
      active: true,
      expires_at: null,
    });
    // CAS update lost the race
    scripts['promo_codes.update'] = [{ data: null, error: null }];
    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(409);
  });

  it('second redeem of same code with no max_uses cap still succeeds (uses increments)', async () => {
    const { POST } = await import('../route');

    // First redeem — uses 0 → 1.
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'FREE',
      discount_pct: 100,
      max_uses: null,
      uses: 0,
      active: true,
      expires_at: null,
    });
    scripts['promo_codes.update'] = [
      { data: { code: 'FREE', uses: 1 }, error: null },
    ];
    scripts['organization_billing.upsert'] = [{ data: null, error: null }];
    scripts['organizations.update'] = [{ data: null, error: null }];

    const res1 = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res1.status).toBe(200);
    expect(await res1.json()).toEqual({ ok: true, redirect: '/for-schools/start/brand' });

    const firstUpdate = recorded.find(
      (r) => r.table === 'promo_codes' && r.op === 'update',
    );
    expect(firstUpdate!.payload).toEqual({ uses: 1 });

    // Second redeem against the post-increment row — uses 1 → 2, no cap blocks it.
    resetMocks();
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'FREE',
      discount_pct: 100,
      max_uses: null,
      uses: 1,
      active: true,
      expires_at: null,
    });
    scripts['promo_codes.update'] = [
      { data: { code: 'FREE', uses: 2 }, error: null },
    ];
    scripts['organization_billing.upsert'] = [{ data: null, error: null }];
    scripts['organizations.update'] = [{ data: null, error: null }];

    const res2 = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res2.status).toBe(200);
    expect(await res2.json()).toEqual({ ok: true, redirect: '/for-schools/start/brand' });

    const secondUpdate = recorded.find(
      (r) => r.table === 'promo_codes' && r.op === 'update',
    );
    expect(secondUpdate!.payload).toEqual({ uses: 2 });
    expect(secondUpdate!.filters).toEqual(
      expect.arrayContaining([
        ['code', 'FREE'],
        ['uses', 1],
        ['active', true],
      ]),
    );
  });

  it('happy path: returns {ok:true, redirect} and writes billing + activates org', async () => {
    mockAuth(USER);
    scriptOwner();
    scriptPromo({
      code: 'FREE',
      discount_pct: 100,
      max_uses: null,
      uses: 7,
      active: true,
      expires_at: null,
    });
    scripts['promo_codes.update'] = [
      { data: { code: 'FREE', uses: 8 }, error: null },
    ];
    scripts['organization_billing.upsert'] = [{ data: null, error: null }];
    scripts['organizations.update'] = [{ data: null, error: null }];

    const { POST } = await import('../route');
    const res = await POST(
      jsonReq({ code: 'FREE', orgId: ORG, tier: 'starter', cycle: 'monthly' }) as never,
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ ok: true, redirect: '/for-schools/start/brand' });

    // Verify the CAS update was scoped by current uses (race safety).
    const updateRow = recorded.find(
      (r) => r.table === 'promo_codes' && r.op === 'update',
    );
    expect(updateRow).toBeDefined();
    expect(updateRow!.payload).toEqual({ uses: 8 });
    expect(updateRow!.filters).toEqual(
      expect.arrayContaining([
        ['code', 'FREE'],
        ['uses', 7],
        ['active', true],
      ]),
    );

    // Verify billing upsert shape mirrors the Whop webhook (org_id, plan, cycle).
    const billingRow = recorded.find(
      (r) => r.table === 'organization_billing' && r.op === 'upsert',
    );
    expect(billingRow).toBeDefined();
    expect(billingRow!.payload).toEqual({
      organization_id: ORG,
      plan: 'starter',
      billing_cycle: 'monthly',
    });

    // Verify org activation.
    const orgUpdate = recorded.find(
      (r) => r.table === 'organizations' && r.op === 'update',
    );
    expect(orgUpdate).toBeDefined();
    expect(orgUpdate!.payload).toEqual({ status: 'active' });
    expect(orgUpdate!.filters).toEqual(expect.arrayContaining([['id', ORG]]));
  });
});
