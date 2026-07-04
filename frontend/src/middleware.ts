import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'
import { NextFetchEvent, NextRequest, NextResponse } from 'next/server'

const isPublicRoute = createRouteMatcher([
  '/sign-in(.*)',
  '/sign-up(.*)',
  '/',
  '/opponent(.*)',
  '/editor(.*)',
  '/position(.*)',
  '/dashboard(.*)',
  '/game(.*)',
  '/learn(.*)',
  '/database(.*)',
  '/profile(.*)',
  '/puzzle(.*)',
  '/play(.*)',
  '/settings(.*)',
  '/onboarding(.*)',
  '/tournaments(.*)',
  '/leaderboard(.*)',
  '/preview(.*)',
  '/for-schools',  // Marketing landing (auth-gated wizard lives under /for-schools/start/*)
  '/api/(.*)',  // Allow all API routes without auth
])

const isSuperAdminRoute = createRouteMatcher(['/super-admin(.*)'])

const clerk = clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect()
  }
})

// Subdomain variant: still runs clerkMiddleware so `auth()` works in
// server components, but never calls auth.protect() — the per-page layout
// (e.g. src/app/admin/layout.tsx) handles unauthenticated redirects and
// sends them to the apex sign-in.
const clerkPassThrough = clerkMiddleware(async () => {
  // no-op: populates auth context, enforces nothing
})

function clearClerkCookies(request: NextRequest, redirectPath: string) {
  const url = new URL(redirectPath, request.url)
  const response = NextResponse.redirect(url)
  for (const { name } of request.cookies.getAll()) {
    if (name.startsWith('__clerk') || name.startsWith('__session') || name.startsWith('__client')) {
      response.cookies.delete(name)
    }
  }
  return response
}

/**
 * Extract org slug from subdomain.
 * e.g. "almatychess.chesster.io" -> "almatychess"
 * Returns null for main domain (chesster.io, www.chesster.io, localhost).
 */
export function extractOrgSlug(request: NextRequest): string | null {
  const host = request.headers.get('host') || ''

  // Dev mode: use ?org=slug query param
  if (host.startsWith('localhost')) {
    return request.nextUrl.searchParams.get('org')
  }

  // Production: extract subdomain from *.chesster.io
  const parts = host.split('.')
  // e.g. ["almatychess", "chesster", "io"] -> subdomain = "almatychess"
  if (parts.length >= 3 && parts.slice(-2).join('.') === 'chesster.io') {
    const subdomain = parts.slice(0, -2).join('.')
    if (subdomain === 'www' || subdomain === '') return null
    return subdomain
  }

  return null
}

/**
 * True when the request is on the apex domain (chesster.io / www.chesster.io)
 * or in localhost dev. Subdomains like school.chesster.io return false.
 */
export function isApexHost(request: NextRequest): boolean {
  const host = (request.headers.get('host') || '').split(':')[0]
  if (host === 'chesster.io' || host === 'www.chesster.io') return true
  if (host === 'localhost' || host === '127.0.0.1' || host.startsWith('localhost')) return true
  return false
}

// In-memory cache for org lookups (TTL: 5 minutes)
const orgCache = new Map<string, { data: Record<string, string>; expiry: number }>()
const customDomainCache = new Map<string, { data: Record<string, string> | null; expiry: number }>()
const ORG_CACHE_TTL = 5 * 60 * 1000

async function lookupOrg(slug: string): Promise<{ id: string; slug: string } | null> {
  const now = Date.now()
  const cached = orgCache.get(slug)
  if (cached && cached.expiry > now) {
    return cached.data as unknown as { id: string; slug: string }
  }

  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001'
    const res = await fetch(`${backendUrl}/api/admin/organizations/by-slug/${slug}`, {
      signal: AbortSignal.timeout(3000),
    })
    if (!res.ok) return null
    const data = await res.json()
    orgCache.set(slug, { data, expiry: now + ORG_CACHE_TTL })
    return data
  } catch {
    return null
  }
}

async function lookupOrgByCustomDomain(host: string): Promise<{ id: string; slug: string } | null> {
  const now = Date.now()
  const cached = customDomainCache.get(host)
  if (cached && cached.expiry > now) {
    return cached.data as unknown as { id: string; slug: string } | null
  }

  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001'
    const res = await fetch(
      `${backendUrl}/api/admin/organizations/by-custom-domain/${encodeURIComponent(host)}`,
      { signal: AbortSignal.timeout(3000) },
    )
    if (!res.ok) {
      // Cache negative lookups too — avoids hammering the backend with 404s
      // from spam hosts. TTL keeps a recovery window short.
      customDomainCache.set(host, { data: null, expiry: now + ORG_CACHE_TTL })
      return null
    }
    const data = await res.json()
    customDomainCache.set(host, { data, expiry: now + ORG_CACHE_TTL })
    return data
  } catch {
    return null
  }
}

/**
 * Resolve the org behind a request. Order: apex → subdomain → custom domain.
 * Returns null for the apex (chesster.io / www) where no org is implied.
 */
export async function resolveOrg(
  request: NextRequest,
): Promise<{ id: string; slug: string } | null> {
  if (isApexHost(request)) return null
  const slug = extractOrgSlug(request)
  if (slug) return lookupOrg(slug)
  const host = (request.headers.get('host') || '').split(':')[0].toLowerCase()
  if (!host) return null
  return lookupOrgByCustomDomain(host)
}

export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  // Extract org slug from subdomain
  const orgSlug = extractOrgSlug(request)
  const host = (request.headers.get('host') || '').split(':')[0].toLowerCase()
  // A custom-domain request: not the apex, no subdomain match → resolve by host.
  const isCustomDomain = !isApexHost(request) && !orgSlug && !!host

  // Phase 7A: gate /super-admin/* on apex host only.
  // A subdomain (school.chesster.io) or custom domain seeing /super-admin must
  // be redirected to the apex equivalent — the route is not exposed on partner
  // hosts.
  if (isSuperAdminRoute(request) && !isApexHost(request)) {
    const apexUrl = new URL(request.nextUrl.pathname + request.nextUrl.search, 'https://chesster.io')
    return NextResponse.redirect(apexUrl, 308)
  }

  // Tenant subdomain / custom-domain branch: skip auth.protect() so unauthenticated
  // requests are not rejected at the edge — the page-level layout decides whether
  // to redirect to the apex sign-in. clerkMiddleware still runs so `auth()` in
  // server components has a populated request context.
  const isTenantHost = !!orgSlug || isCustomDomain
  const clerkFn = isTenantHost ? clerkPassThrough : clerk

  // Forward the original pathname to server components so the admin layout
  // can build a redirect_url back to the originating tenant URL post sign-in.
  if (isTenantHost) {
    request.headers.set('x-pathname', request.nextUrl.pathname)
  }

  // Resolve the tenant org BEFORE Clerk runs and mutate the *request* headers
  // (not the response) so React Server Components can read `x-org-id` /
  // `x-org-slug` via `headers()`. Response headers set after clerkFn go to the
  // browser, not to RSC — that pipeline was silently broken and caused
  // /dashboard on chess-empire.chesster.io to skip the personalized delegation
  // and fall through to the generic Chesster dashboard.
  let resolvedOrg: { id: string; slug: string } | null = null
  if (orgSlug) {
    resolvedOrg = await lookupOrg(orgSlug)
  } else if (isCustomDomain) {
    resolvedOrg = await lookupOrgByCustomDomain(host)
  }
  if (resolvedOrg) {
    request.headers.set('x-org-id', resolvedOrg.id)
    request.headers.set('x-org-slug', resolvedOrg.slug)
  }

  try {
    const response = await clerkFn(request, event)
    // If Clerk returned a 500 (e.g., kid mismatch during handshake), clear cookies
    if (response && response.status >= 500) {
      return clearClerkCookies(request, request.nextUrl.pathname)
    }

    const res = response ?? NextResponse.next()

    // Mirror the resolved org on the response headers as well — a handful of
    // downstream helpers (org-name-from-host.ts comment, tests) and any
    // future edge inspection tooling can still read them there without
    // re-hitting the backend.
    if (resolvedOrg) {
      res.headers.set('x-org-id', resolvedOrg.id)
      res.headers.set('x-org-slug', resolvedOrg.slug)
    }

    return res
  } catch {
    // Stale Clerk session (key rotation, instance change) — clear cookies and redirect
    return clearClerkCookies(request, request.nextUrl.pathname)
  }
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|mjs|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|lottie|json|wasm|onnx)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
