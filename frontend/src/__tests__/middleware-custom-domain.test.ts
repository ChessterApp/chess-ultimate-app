import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@clerk/nextjs/server', () => ({
  clerkMiddleware: (handler: (auth: { protect: () => Promise<void> }, req: NextRequest) => Promise<void>) => {
    return async (req: NextRequest) => {
      let protectCalled = false;
      const fakeAuth = {
        protect: async () => {
          protectCalled = true;
        },
      };
      await handler(fakeAuth, req);
      const hasSession = req.cookies?.get?.('__session');
      if (protectCalled && !hasSession) {
        const signInUrl = new URL('/sign-in', req.url);
        return Response.redirect(signInUrl, 307);
      }
      const { NextResponse } = await import('next/server');
      return NextResponse.next();
    };
  },
  createRouteMatcher: (patterns: string[]) => (req: NextRequest) => {
    const path = new URL(req.url).pathname;
    return patterns.some(p => {
      const regex = new RegExp('^' + p.replace(/\(\.\*\)/g, '.*').replace(/\//g, '\\/') + '$');
      return regex.test(path);
    });
  },
}));

function makeRequest(url: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(new URL(url), {
    headers: { host: new URL(url).host, ...headers },
  });
}

describe('resolveOrg — custom domain', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it('returns null on the apex host', async () => {
    const { resolveOrg } = await import('../middleware');
    const req = makeRequest('https://chesster.io/', { host: 'chesster.io' });
    expect(await resolveOrg(req)).toBeNull();
  });

  it('resolves via subdomain when slug is present', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'org-uuid-sub', slug: 'demo' }),
    }) as unknown as typeof fetch;

    const { resolveOrg } = await import('../middleware');
    const req = makeRequest('https://demo.chesster.io/', { host: 'demo.chesster.io' });
    const org = await resolveOrg(req);
    expect(org).toEqual({ id: 'org-uuid-sub', slug: 'demo' });
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain('/by-slug/demo');
  });

  it('resolves a custom domain when not apex and not a chesster.io subdomain', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'org-uuid-cd', slug: 'almatychess' }),
    }) as unknown as typeof fetch;

    const { resolveOrg } = await import('../middleware');
    const req = makeRequest('https://chess.example.com/', { host: 'chess.example.com' });
    const org = await resolveOrg(req);
    expect(org).toEqual({ id: 'org-uuid-cd', slug: 'almatychess' });
    expect((global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain(
      '/by-custom-domain/chess.example.com',
    );
  });

  it('returns null on unknown host (backend 404)', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;
    const { resolveOrg } = await import('../middleware');
    const req = makeRequest('https://random-host.test/', { host: 'random-host.test' });
    expect(await resolveOrg(req)).toBeNull();
  });

  it('cache hit skips the second fetch', async () => {
    const f = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'org-uuid-cd', slug: 'almatychess' }),
    });
    global.fetch = f as unknown as typeof fetch;

    const { resolveOrg } = await import('../middleware');
    const req1 = makeRequest('https://cached-host.example.com/', { host: 'cached-host.example.com' });
    const req2 = makeRequest('https://cached-host.example.com/some/path', { host: 'cached-host.example.com' });
    await resolveOrg(req1);
    await resolveOrg(req2);
    expect(f).toHaveBeenCalledTimes(1);
  });
});

describe('middleware integration with custom domains', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it('skips auth.protect and injects org headers for custom domain', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'org-uuid-cd2', slug: 'almatychess' }),
    }) as unknown as typeof fetch;

    const middleware = (await import('../middleware')).default;
    const req = makeRequest('https://chess.almaty-cd2.example.com/admin/dashboard',
      { host: 'chess.almaty-cd2.example.com' });
    const event = { waitUntil: () => {} } as unknown as Parameters<typeof middleware>[1];
    const res = await middleware(req, event);

    expect(res).toBeTruthy();
    expect(res!.headers.get('x-org-id')).toBe('org-uuid-cd2');
    expect(res!.headers.get('x-org-slug')).toBe('almatychess');
    // Custom domain hosts also forward x-pathname so admin layout can build redirect_url
    expect(req.headers.get('x-pathname')).toBe('/admin/dashboard');
    // Auth.protect was not called → no redirect
    expect(res!.status).toBe(200);
  });

  it('custom-domain hit followed by sign-in redirect happens on apex (super-admin guard still active)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'x', slug: 'almatychess' }),
    }) as unknown as typeof fetch;

    const middleware = (await import('../middleware')).default;
    const req = makeRequest('https://chess.super-test.example.com/super-admin/foo',
      { host: 'chess.super-test.example.com' });
    const event = { waitUntil: () => {} } as unknown as Parameters<typeof middleware>[1];
    const res = await middleware(req, event);

    expect(res!.status).toBe(308);
    expect(res!.headers.get('location')).toBe('https://chesster.io/super-admin/foo');
  });
});
