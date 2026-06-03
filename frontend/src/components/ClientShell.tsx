"use client"

import { usePathname } from "next/navigation"
import { Suspense, type ReactNode, lazy } from "react"
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

// Lazy load MUI provider only when needed
const MuiProvider = lazy(() => import("@/components/providers/MuiProvider"))

// Pages where the navigation should be hidden
const HIDE_NAV_PATHS = ['/sign-in', '/sign-up', '/', '/onboarding', '/admin', '/for-schools/start']

// Routes that use MUI components and need ThemeProvider
const MUI_ROUTES = ['/database', '/game', '/position', '/puzzle', '/repertoire', '/practice', '/courses']

export default function ClientShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const hideNav = HIDE_NAV_PATHS.some(path => pathname === path || (path !== '/' && pathname?.startsWith(path)))
  const isLanding = pathname === '/'

  // Apply dark mode class to <html> on every page load
  const { isDark } = useDarkMode()

  // Keyboard shortcuts
  const { showHelp, setShowHelp } = useKeyboardShortcuts()

  // Check if current route needs MUI components
  const needsMui = MUI_ROUTES.some(route => pathname?.startsWith(route))

  const content = (
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

            {/* Mobile top navbar — hidden on desktop, hidden on auth pages */}
            {!hideNav && (
              <div className="md:hidden">
                <NavBar />
              </div>
            )}

            {/* Main content area */}
            <main className={`flex-1 min-w-0 ${hideNav ? '' : 'pb-16 md:pb-0'}`}>
              <Suspense fallback={<PageSkeleton />}>
                <SyncBoundary>
                  {hideNav ? children : <PageTransition>{children}</PageTransition>}
                </SyncBoundary>
              </Suspense>
            </main>

            {/* Mobile bottom nav — hidden on desktop, hidden on auth pages */}
            {!hideNav && (
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
