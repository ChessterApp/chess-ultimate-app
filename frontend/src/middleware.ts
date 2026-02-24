import { clerkMiddleware, createRouteMatcher } from '@clerk/nextjs/server'

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

export default clerkMiddleware(async (auth, request) => {
  if (!isPublicRoute(request)) {
    await auth.protect()
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest|lottie|json)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
