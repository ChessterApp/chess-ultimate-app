"use client"

import { usePathname } from "next/navigation"
import { Suspense, useEffect, useState, type ReactNode, lazy } from "react"
import { warmStockfish } from "@/lib/engine/stockfishSingleton"
import { prewarmMaiaDownload } from "@/lib/engine/maiaSingleton"
import PageTransition from "@/components/PageTransition"
import OfflineBanner from "@/components/OfflineBanner"
import ToastProvider from "@/components/ToastProvider"
import SubscriptionProvider from "@/components/SubscriptionProvider"
import UnhandledErrorCatcher from "@/components/UnhandledErrorBoundary"
import PageSkeleton from "@/components/PageSkeleton"
import NavBar from "@/components/Navbar"
import { BottomNavigation } from "@/components/ui/BottomNavigation"
import DesktopSidebar from "@/components/ui/DesktopSidebar"
import { useDarkMode } from "@/hooks/useDarkMode"
import { useKeyboardShortcuts } from "@/hooks/useKeyboardShortcuts"
import KeyboardShortcutsHelp from "@/components/KeyboardShortcutsHelp"
import SyncBoundary from "@/components/SyncBoundary"
import SyncIndicator from "@/components/SyncIndicator"
import { ChromeVisibilityProvider } from "@/components/ChromeVisibilityContext"

// Lazy load MUI provider only when needed
const MuiProvider = lazy(() => import("@/components/providers/MuiProvider"))

// Pages where the navigation should be hidden
const HIDE_NAV_PATHS = ['/sign-in', '/sign-up', '/', '/onboarding', '/admin', '/for-schools/start', '/landing-test', '/games/tug-of-war']

// Routes that use MUI components and need ThemeProvider
const MUI_ROUTES = ['/database', '/game', '/position', '/puzzle', '/practice', '/courses']

export default function ClientShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const hideNav = HIDE_NAV_PATHS.some(path => pathname === path || (path !== '/' && pathname?.startsWith(path)))
  const isLanding = pathname === '/'

  // A full-screen page (the in-game /play screen) can hide the mobile chrome —
  // top NavBar + BottomNavigation — while a game is active. The desktop sidebar
  // is intentionally left untouched. Reset by the page on unmount/phase change.
  const [chromeHidden, setChromeHidden] = useState(false)
  const mobileNavHidden = hideNav || chromeHidden

  // Apply dark mode class to <html> on every page load
  const { isDark } = useDarkMode()

  // Keyboard shortcuts
  const { showHelp, setShowHelp } = useKeyboardShortcuts()

  // Check if current route needs MUI components
  const needsMui = MUI_ROUTES.some(route => pathname?.startsWith(route))

  // Pre-warm engines once the browser is idle so the first visit to /play feels
  // instant. Stockfish (7MB) is warmed, and the Maia model download is kicked
  // off in the background too (skipped on Save-Data connections) — so a
  // first-time visitor never has to wait on the ~24MB download at /play.
  useEffect(() => {
    if (typeof window === "undefined") return
    const prewarm = () => {
      warmStockfish()
      prewarmMaiaDownload()
    }
    const ric = window.requestIdleCallback
    if (ric) {
      const id = ric(prewarm)
      return () => window.cancelIdleCallback?.(id)
    }
    const id = window.setTimeout(prewarm, 2000)
    return () => window.clearTimeout(id)
  }, [])

  const content = (
    <ChromeVisibilityProvider value={{ setChromeHidden }}>
    <ToastProvider>
      <SubscriptionProvider>
        <UnhandledErrorCatcher />
        <OfflineBanner>
          <div className={!hideNav && !isLanding ? "md:flex min-h-screen" : ""}>
            {/* Desktop sidebar — hidden on mobile, auth pages, and landing */}
            {!hideNav && !isLanding && (
              <div className="hidden md:block flex-shrink-0 overflow-visible relative z-20">
                <DesktopSidebar />
              </div>
            )}

            {/* Mobile top navbar — hidden on desktop, hidden on auth pages,
                hidden while an in-game page requests full-screen chrome. */}
            {!mobileNavHidden && (
              <div className="md:hidden">
                <NavBar />
              </div>
            )}

            {/* Main content area */}
            <main className={`flex-1 min-w-0 ${mobileNavHidden ? '' : 'pb-16 md:pb-0'}`}>
              <Suspense fallback={<PageSkeleton />}>
                {/* Static marketing test page — no user data, skip the sync gate */}
                {pathname?.startsWith('/landing-test') ? children : (
                  <SyncBoundary>
                    {hideNav ? children : <PageTransition>{children}</PageTransition>}
                  </SyncBoundary>
                )}
              </Suspense>
            </main>

            {/* Mobile bottom nav — hidden on desktop, hidden on auth pages,
                hidden while an in-game page requests full-screen chrome. */}
            {!mobileNavHidden && (
              <div className="md:hidden">
                <BottomNavigation />
              </div>
            )}
          </div>
          <KeyboardShortcutsHelp open={showHelp} onClose={() => setShowHelp(false)} />
          <SyncIndicator />
        </OfflineBanner>
      </SubscriptionProvider>
    </ToastProvider>
    </ChromeVisibilityProvider>
  )

  // Conditionally wrap with MUI provider only on routes that need it
  if (needsMui) {
    return (
      <Suspense fallback={<PageSkeleton />}>
        <MuiProvider>{content}</MuiProvider>
      </Suspense>
    )
  }

  return content
}
