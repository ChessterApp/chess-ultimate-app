import { NextRequest, NextResponse } from 'next/server';

/**
 * In-memory org slug cache with 5-minute TTL.
 * Maps slug -> { orgId, orgSlug, timestamp }.
 * Edge middleware runs on every request, so we cache to avoid DB lookups.
 */
interface OrgCacheEntry {
  orgId: string;
  slug: string;
  timestamp: number;
}

const ORG_CACHE = new Map<string, OrgCacheEntry | null>();
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

const MAIN_DOMAIN = 'chesster.io';

/**
 * Reserved subdomains that should not be treated as org slugs.
 */
const RESERVED_SUBDOMAINS = new Set(['www', 'api', 'app', 'admin', 'mail', 'staging']);

/**
 * Extract the org slug from the request.
 * - Production: subdomain of chesster.io (e.g., almatychess.chesster.io -> "almatychess")
 * - Development: ?org=slug query param on localhost
 */
function extractOrgSlug(request: NextRequest): string | null {
  const host = request.headers.get('host') || '';

  // Dev mode: use ?org= query param
  if (host.startsWith('localhost') || host.startsWith('127.0.0.1')) {
    return request.nextUrl.searchParams.get('org') || null;
  }

  // Production: extract subdomain from host
  // e.g., "almatychess.chesster.io" -> "almatychess"
  if (host.endsWith(`.${MAIN_DOMAIN}`)) {
    const subdomain = host.slice(0, -(MAIN_DOMAIN.length + 1)); // strip ".chesster.io"
    if (!subdomain || RESERVED_SUBDOMAINS.has(subdomain)) {
      return null;
    }
    return subdomain;
  }

  return null;
}

/**
 * Lookup org by slug. Uses in-memory cache with 5-minute TTL.
 * Returns the cached entry or fetches from Supabase.
 *
 * For now, we validate the slug format and set headers.
 * The actual Supabase lookup will use the backend API once available.
 * In production, this will be replaced with an edge-compatible fetch.
 */
async function lookupOrg(slug: string): Promise<OrgCacheEntry | null> {
  const now = Date.now();

  // Check cache
  if (ORG_CACHE.has(slug)) {
    const cached = ORG_CACHE.get(slug);
    if (cached && now - cached.timestamp < CACHE_TTL_MS) {
      return cached;
    }
    // Expired or null entry - remove and re-fetch
    ORG_CACHE.delete(slug);
  }

  // Fetch org from backend API
  try {
    const backendUrl = process.env.INTERNAL_BACKEND_URL || 'http://localhost:5001';
    const response = await fetch(`${backendUrl}/api/organizations/by-slug/${slug}`, {
      headers: { 'x-internal-request': 'true' },
      signal: AbortSignal.timeout(3000),
    });

    if (response.ok) {
      const data = await response.json();
      const entry: OrgCacheEntry = {
        orgId: data.id,
        slug: data.slug,
        timestamp: now,
      };
      ORG_CACHE.set(slug, entry);
      return entry;
    }
  } catch {
    // Backend unavailable - pass through without org context
  }

  // Cache negative result for shorter TTL (1 minute)
  ORG_CACHE.set(slug, null);
  setTimeout(() => ORG_CACHE.delete(slug), 60_000);
  return null;
}

/**
 * Check if the user has admin access for the given org.
 * This is a lightweight check using a cookie or header set during auth.
 * Full RBAC is enforced server-side via RLS and API checks.
 */
function hasAdminAccess(request: NextRequest): boolean {
  // The org role is set in a cookie by the auth flow
  const orgRole = request.cookies.get('org-role')?.value;
  return orgRole === 'owner' || orgRole === 'admin' || orgRole === 'teacher';
}

export async function middleware(request: NextRequest) {
  const slug = extractOrgSlug(request);

  // No org context - pass through to normal Chesster
  if (!slug) {
    return NextResponse.next();
  }

  // Lookup the org
  const org = await lookupOrg(slug);

  if (!org) {
    // Unknown org slug - return 404
    return NextResponse.rewrite(new URL('/not-found', request.url));
  }

  // Block /admin routes for non-admin roles
  if (request.nextUrl.pathname.startsWith('/admin')) {
    if (!hasAdminAccess(request)) {
      return NextResponse.redirect(new URL('/dashboard', request.url));
    }
  }

  // Rewrite to tenant-scoped path internally
  const url = request.nextUrl.clone();
  const originalPath = url.pathname;
  url.pathname = `/tenant/${slug}${originalPath}`;

  const response = NextResponse.rewrite(url);

  // Set org headers for downstream use by server components
  response.headers.set('x-org-id', org.orgId);
  response.headers.set('x-org-slug', org.slug);

  return response;
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     * - public files (static assets like images, fonts, etc.)
     * - API routes (handled by rewrites in next.config.ts)
     */
    '/((?!_next/static|_next/image|favicon.ico|static/|animations/|ort/|maia3/|powersync/|sw.js|api/).*)',
  ],
};
