import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';

vi.mock('@clerk/nextjs/server', () => ({
  clerkMiddleware: (handler: (auth: { protect: () => Promise<void> }, req: NextRequest) => Promise<void>) => {
    return async (req: NextRequest) => {
      // Simulate Clerk middleware: invoke handler; if it calls auth.protect()
      // and there's no session cookie, redirect to /sign-in. Otherwise NextResponse.next().
      let protectCalled = false;
      // Real Clerk `auth` is callable (session resolution) and also carries
      // .protect() — the pass-through middleware now calls `await auth()`.
      const fakeAuth = Object.assign(async () => ({ userId: null }), {
        protect: async () => {
          protectCalled = true;
        },
      });
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

describe('middleware host detection', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('isApexHost returns true for chesster.io', async () => {
    const { isApexHost } = await import('../middleware');
    const req = makeRequest('https://chesster.io/', { host: 'chesster.io' });
    expect(isApexHost(req)).toBe(true);
  });

  it('isApexHost returns true for www.chesster.io', async () => {
    const { isApexHost } = await import('../middleware');
    const req = makeRequest('https://www.chesster.io/', { host: 'www.chesster.io' });
    expect(isApexHost(req)).toBe(true);
  });

  it('isApexHost returns true for localhost', async () => {
    const { isApexHost } = await import('../middleware');
    const req = makeRequest('http://localhost:3000/', { host: 'localhost:3000' });
    expect(isApexHost(req)).toBe(true);
  });

  it('isApexHost returns false for tenant subdomain', async () => {
    const { isApexHost } = await import('../middleware');
    const req = makeRequest('https://demo.chesster.io/', { host: 'demo.chesster.io' });
    expect(isApexHost(req)).toBe(false);
  });

  it('extractOrgSlug returns slug for tenant subdomain', async () => {
    const { extractOrgSlug } = await import('../middleware');
    const req = makeRequest('https://demo.chesster.io/admin', { host: 'demo.chesster.io' });
    expect(extractOrgSlug(req)).toBe('demo');
  });

  it('extractOrgSlug returns null for apex', async () => {
    const { extractOrgSlug } = await import('../middleware');
    const req = makeRequest('https://chesster.io/', { host: 'chesster.io' });
    expect(extractOrgSlug(req)).toBeNull();
  });

  it('extractOrgSlug returns null for www subdomain', async () => {
    const { extractOrgSlug } = await import('../middleware');
    const req = makeRequest('https://www.chesster.io/', { host: 'www.chesster.io' });
    expect(extractOrgSlug(req)).toBeNull();
  });

  it('extractOrgSlug reads ?org= param on localhost', async () => {
    const { extractOrgSlug } = await import('../middleware');
    const req = makeRequest('http://localhost:3000/?org=demo', { host: 'localhost:3000' });
    expect(extractOrgSlug(req)).toBe('demo');
  });
});

describe('middleware subdomain branch', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
  });

  it('skips auth.protect on tenant subdomain and injects org headers', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'org-uuid-123', slug: 'demo' }),
    }) as unknown as typeof fetch;

    const middleware = (await import('../middleware')).default;
    const req = makeRequest('https://demo.chesster.io/admin/dashboard', { host: 'demo.chesster.io' });
    const event = { waitUntil: () => {} } as unknown as Parameters<typeof middleware>[1];
    const res = await middleware(req, event);

    expect(res).toBeTruthy();
    expect(res!.headers.get('x-org-id')).toBe('org-uuid-123');
    expect(res!.headers.get('x-org-slug')).toBe('demo');
    // No redirect to sign-in — protect() was not called on subdomain
    expect(res!.status).toBe(200);
    // pathname forwarded for layout to build apex redirect_url
    expect(req.headers.get('x-pathname')).toBe('/admin/dashboard');
  });

  it('apex /admin without session redirects to sign-in (auth.protect runs)', async () => {
    const middleware = (await import('../middleware')).default;
    const req = makeRequest('https://chesster.io/admin/dashboard', { host: 'chesster.io' });
    const event = { waitUntil: () => {} } as unknown as Parameters<typeof middleware>[1];
    const res = await middleware(req, event);

    expect(res!.status).toBe(307);
    expect(res!.headers.get('location')).toContain('/sign-in');
  });

  it('redirects /super-admin/* on subdomain to apex', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'x', slug: 'demo' }),
    }) as unknown as typeof fetch;

    const middleware = (await import('../middleware')).default;
    const req = makeRequest('https://demo.chesster.io/super-admin/tenants', {
      host: 'demo.chesster.io',
    });
    const event = { waitUntil: () => {} } as unknown as Parameters<typeof middleware>[1];
    const res = await middleware(req, event);

    expect(res!.status).toBe(308);
    expect(res!.headers.get('location')).toBe('https://chesster.io/super-admin/tenants');
  });

  it('does not inject org headers when lookup fails', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;

    const middleware = (await import('../middleware')).default;
    const req = makeRequest('https://unknown.chesster.io/', { host: 'unknown.chesster.io' });
    const event = { waitUntil: () => {} } as unknown as Parameters<typeof middleware>[1];
    const res = await middleware(req, event);

    expect(res).toBeTruthy();
    expect(res!.headers.get('x-org-id')).toBeNull();
    expect(res!.headers.get('x-org-slug')).toBeNull();
  });
});

describe('middleware matcher config', () => {
  it('excludes static asset extensions', async () => {
    const { config } = await import('../middleware');
    expect(config.matcher).toBeDefined();
    expect(config.matcher[0]).toContain('_next');
    expect(config.matcher[0]).toContain('webmanifest');
  });
});
