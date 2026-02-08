"use client"

import dynamic from "next/dynamic"
import type { ReactNode } from "react"

// Load all client components with ssr:false to prevent hydration mismatches
// from useAuth(), useLocalStorage(), and Clerk's injected HTML
const NavBar = dynamic(() => import("@/components/Navbar"), { ssr: false })
const BottomNavigation = dynamic(
  () => import("@/components/ui/BottomNavigation").then(mod => ({ default: mod.BottomNavigation })),
  { ssr: false }
)
const BottomNavSpacer = dynamic(
  () => import("@/components/ui/BottomNavigation").then(mod => ({ default: mod.BottomNavSpacer })),
  { ssr: false }
)

export default function ClientShell({ children }: { children: ReactNode }) {
  return (
    <>
      <NavBar />
      <main className="pb-16 md:pb-0">
        {children}
      </main>
      <BottomNavigation />
    </>
  )
}
