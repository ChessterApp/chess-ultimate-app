"use client"

import { usePathname } from "next/navigation"
import { Suspense, type ReactNode } from "react"
import { ThemeProvider } from "@mui/material/styles"
import CssBaseline from "@mui/material/CssBaseline"
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
import { chessterLightTheme, chessterDarkTheme } from "@/theme/theme"

// Pages where the navigation should be hidden
const HIDE_NAV_PATHS = ['/sign-in', '/sign-up', '/', '/onboarding']

export default function ClientShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const hideNav = HIDE_NAV_PATHS.some(path => pathname === path || (path !== '/' && pathname?.startsWith(path)))
  const isLanding = pathname === '/'
  
  // Apply dark mode class to <html> on every page load
  const { isDark } = useDarkMode()
  
  // Keyboard shortcuts
  const { showHelp, setShowHelp } = useKeyboardShortcuts()

  // Select MUI theme based on dark mode state
  const muiTheme = isDark ? chessterDarkTheme : chessterLightTheme

  return (
    <ThemeProvider theme={muiTheme}>
      <CssBaseline enableColorScheme />
      <ToastProvider>
        <SubscriptionProvider>
        <UnhandledErrorCatcher />
        <OfflineBanner />
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
              {hideNav ? children : <PageTransition>{children}</PageTransition>}
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
        </SubscriptionProvider>
      </ToastProvider>
    </ThemeProvider>
  )
}
