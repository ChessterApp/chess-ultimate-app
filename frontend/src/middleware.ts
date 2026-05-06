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
  '/api/(.*)',  // Allow all API routes without auth
])

const isSuperAdminRoute = createRouteMatcher(['/super-admin(.*)'])

const clerk = clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect()
  }
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
function extractOrgSlug(request: NextRequest): string | null {
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
function isApexHost(request: NextRequest): boolean {
  const host = (request.headers.get('host') || '').split(':')[0]
  if (host === 'chesster.io' || host === 'www.chesster.io') return true
  if (host === 'localhost' || host === '127.0.0.1' || host.startsWith('localhost')) return true
  return false
}

// In-memory cache for org lookups (TTL: 5 minutes)
const orgCache = new Map<string, { data: Record<string, string>; expiry: number }>()
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

export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  // Extract org slug from subdomain
  const orgSlug = extractOrgSlug(request)

  // Phase 7A: gate /super-admin/* on apex host only.
  // A subdomain (school.chesster.io) seeing /super-admin must be redirected
  // to the apex equivalent — the route is not exposed on partner subdomains.
  if (isSuperAdminRoute(request) && !isApexHost(request)) {
    const apexUrl = new URL(request.nextUrl.pathname + request.nextUrl.search, 'https://chesster.io')
    return NextResponse.redirect(apexUrl, 308)
  }

  try {
    const response = await clerk(request, event)
    // If Clerk returned a 500 (e.g., kid mismatch during handshake), clear cookies
    if (response && response.status >= 500) {
      return clearClerkCookies(request, request.nextUrl.pathname)
    }

    const res = response ?? NextResponse.next()

    // Inject org headers if subdomain detected
    if (orgSlug) {
      const org = await lookupOrg(orgSlug)
      if (org) {
        res.headers.set('x-org-id', org.id)
        res.headers.set('x-org-slug', org.slug)
      }
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
