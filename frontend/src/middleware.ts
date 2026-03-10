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
  '/debut(.*)',
  '/profile(.*)',
  '/puzzle(.*)',
  '/settings(.*)',
  '/onboarding(.*)',
  '/api/(.*)',  // Allow all API routes without auth
])

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

export default async function middleware(request: NextRequest, event: NextFetchEvent) {
  try {
    const response = await clerk(request, event)
    // If Clerk returned a 500 (e.g., kid mismatch during handshake), clear cookies
    if (response.status >= 500) {
      return clearClerkCookies(request, request.nextUrl.pathname)
    }
    return response
  } catch {
    // Stale Clerk session (key rotation, instance change) — clear cookies and redirect
    return clearClerkCookies(request, request.nextUrl.pathname)
  }
}

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|lottie|json|wasm)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
