/**
 * Tests for POST /api/chess-empire/gamification/sync-request.
 *
 * The browser-callable gamification trigger: the CE admin app POSTs its
 * Supabase user access token; we verify it against the CE project and, on a
 * valid token, run `syncOrg` for every org with a gamification_settings row.
 *
 * Covers: 401 (no header), 401 (verification fails), 200 + syncOrg per org,
 * 202 cooldown on an immediate second call (syncOrg NOT re-run), OPTIONS CORS
 * preflight, and the CORS header on POST responses.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

// Mutable per-test result for the CE supabase `auth.getUser` verification.
let getUserResult: { data: { user: unknown }; error: unknown } = {
  data: { user: null },
  error: null,
};

vi.mock('@supabase/supabase-js', () => ({
  createClient: () => ({
    auth: { getUser: () => Promise.resolve(getUserResult) },
  }),
}));

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => ({
      select: () =>
        Promise.resolve({
          data: [{ organization_id: 'org-1' }, { organization_id: 'org-2' }],
          error: null,
        }),
    }),
  },
}));

const syncOrg = vi.fn();
vi.mock('@/lib/gamification/sync-run', () => ({
  syncOrg: (orgId: string) => syncOrg(orgId),
}));

function makeReq(headers: Record<string, string> = {}): NextRequest {
  return new NextRequest('http://x/api/chess-empire/gamification/sync-request', {
    method: 'POST',
    headers,
  });
}

// Fresh module state (in-flight/cooldown) per test.
async function freshPost() {
  vi.resetModules();
  const mod = await import('../route');
  return mod.POST;
}

beforeEach(() => {
  vi.clearAllMocks();
  process.env.CHESS_EMPIRE_SUPABASE_URL = 'https://ce.supabase.co';
  process.env.CHESS_EMPIRE_SERVICE_KEY = 'ce-service-key';
  getUserResult = { data: { user: null }, error: null };
  syncOrg.mockResolvedValue({ organization_id: 'org', awarded: 0 });
});

describe('POST /api/chess-empire/gamification/sync-request', () => {
  it('401 when no Authorization header', async () => {
    const POST = await freshPost();
    const res = await POST(makeReq());
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: 'Unauthorized' });
    expect(syncOrg).not.toHaveBeenCalled();
  });

  it('401 when token verification fails', async () => {
    getUserResult = { data: { user: null }, error: { message: 'bad jwt' } };
    const POST = await freshPost();
    const res = await POST(makeReq({ authorization: 'Bearer bogus' }));
    expect(res.status).toBe(401);
    expect(await res.json()).toEqual({ error: 'Unauthorized' });
    expect(syncOrg).not.toHaveBeenCalled();
  });

  it('401 when CE env is missing (fail closed)', async () => {
    delete process.env.CHESS_EMPIRE_SUPABASE_URL;
    getUserResult = { data: { user: { id: 'u1' } }, error: null };
    const POST = await freshPost();
    const res = await POST(makeReq({ authorization: 'Bearer good' }));
    expect(res.status).toBe(401);
    expect(syncOrg).not.toHaveBeenCalled();
  });

  it('200 and runs syncOrg per org when token is valid', async () => {
    getUserResult = { data: { user: { id: 'u1' } }, error: null };
    const POST = await freshPost();
    const res = await POST(makeReq({ authorization: 'Bearer good' }));
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.ok).toBe(true);
    expect(typeof body.ran_at).toBe('string');
    expect(body.orgs).toHaveLength(2);
    expect(syncOrg).toHaveBeenCalledTimes(2);
    expect(syncOrg).toHaveBeenCalledWith('org-1');
    expect(syncOrg).toHaveBeenCalledWith('org-2');
  });

  it('second immediate call returns 202 cooldown and does not re-run syncOrg', async () => {
    getUserResult = { data: { user: { id: 'u1' } }, error: null };
    const POST = await freshPost();
    const first = await POST(makeReq({ authorization: 'Bearer good' }));
    expect(first.status).toBe(200);
    expect(syncOrg).toHaveBeenCalledTimes(2);

    const second = await POST(makeReq({ authorization: 'Bearer good' }));
    expect(second.status).toBe(202);
    expect(await second.json()).toEqual({ ok: true, skipped: 'cooldown' });
    // syncOrg not called again — still exactly the first run's 2 invocations.
    expect(syncOrg).toHaveBeenCalledTimes(2);
  });

  it('OPTIONS returns 204 with CORS headers', async () => {
    vi.resetModules();
    const { OPTIONS } = await import('../route');
    const res = await OPTIONS();
    expect(res.status).toBe(204);
    expect(res.headers.get('access-control-allow-origin')).toBe('*');
    expect(res.headers.get('access-control-allow-methods')).toBe('POST, OPTIONS');
    expect(res.headers.get('access-control-allow-headers')).toBe(
      'authorization, content-type',
    );
  });

  it('sets the CORS origin header on POST responses', async () => {
    // 401 path
    const POST401 = await freshPost();
    const res401 = await POST401(makeReq());
    expect(res401.headers.get('access-control-allow-origin')).toBe('*');

    // 200 path
    getUserResult = { data: { user: { id: 'u1' } }, error: null };
    const POST200 = await freshPost();
    const res200 = await POST200(makeReq({ authorization: 'Bearer good' }));
    expect(res200.status).toBe(200);
    expect(res200.headers.get('access-control-allow-origin')).toBe('*');
  });
});
