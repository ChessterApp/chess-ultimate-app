# PRD: Chesster Performance Optimization — Phase 1

## Goal
Reduce perceived page load time to <100ms. Currently ~400-500ms.

## Context
- Next.js 16, React 19, standalone output
- 17/18 pages are `'use client'` — zero pre-rendering
- Service worker uses network-first for HTML
- MUI ThemeProvider loaded on every page
- VPS serves via PM2 port 3000, Vercel serves chesster.io

## Checklist

### 1. Convert Landing Page to Server Component
- [x] Remove `'use client'` from `src/app/page.tsx`
- [x] Extract interactive parts (auth buttons, language switcher, animations) into small client islands
- [x] Keep the main HTML structure as a server component for instant pre-rendering
- [x] Add `export const revalidate = 3600` for ISR (rebuild hourly)
- [x] Test: `curl -s https://vps.chesster.io/ | head -100` should show pre-rendered HTML content (not empty div)

### 2. Service Worker: Stale-While-Revalidate
- [x] In `public/sw.js`, change navigation requests from network-first to stale-while-revalidate
- [x] Pattern: serve cached version immediately, fetch fresh in background, update cache
- [x] Keep API requests as network-first with cache fallback
- [x] Precache critical page shells: `/`, `/dashboard`, `/debut`, `/learn`, `/puzzle`
- [x] Bump cache version to `chesster-v5`
- [x] Update version in ServiceWorkerRegistration.tsx to `?v=4`

### 3. Add Cache Headers for ISR Pages
- [x] In `next.config.ts`, add headers for pages that use ISR:
  - `Cache-Control: public, s-maxage=3600, stale-while-revalidate=86400` for landing page
- [x] For API responses that are semi-static (courses, popular openings), add `Cache-Control: public, max-age=300`

### 4. App Shell Pattern with Suspense
- [x] In `src/components/ClientShell.tsx`, wrap `{children}` with `<Suspense fallback={<PageSkeleton />}>`
- [x] Create a lightweight `PageSkeleton` component that shows the layout structure instantly
- [x] This ensures navigation sidebar/topbar renders immediately while page content loads

### 5. Lazy Import Heavy Dependencies
- [x] In pages that import chess.js, use `dynamic(() => import(...), { ssr: false })` or lazy React imports
- [x] In ClientShell.tsx, make MUI ThemeProvider dynamic only when needed (or keep but ensure tree-shaking)
- [x] Move `@ai-sdk/*` imports to dynamic in analysis pages only
- [x] Move `framer-motion` to dynamic import where used

### 6. Prefetch High-Traffic Routes
- [x] In the landing page, add explicit `<Link prefetch>` for `/dashboard`, `/learn`, `/debut`, `/puzzle`
- [x] After initial page load, programmatically prefetch top 3 routes via `router.prefetch()`

## Constraints
- Do NOT change the Clerk auth flow
- Do NOT change routing structure
- Do NOT break the standalone build output
- Always `export HOME=/root` before git/pm2
- Never `git add -A` — add specific files
- Test with `npm run build` before committing
- Run `curl localhost:3000` after PM2 restart to verify

## Definition of Done
- Landing page renders pre-built HTML (visible in curl output)
- Service worker serves cached pages instantly on repeat visits
- Build succeeds without errors
- PM2 serves the app correctly
- All pages still function (auth, navigation, data loading)
