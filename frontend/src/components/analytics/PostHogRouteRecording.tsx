'use client'

import { useEffect } from 'react'
import { usePathname } from 'next/navigation'
import posthog from 'posthog-js'

// Session replay only runs on marketing/funnel pages — never inside the app
// where kids play, chat with the coach, or use voice mode.
const RECORDING_PREFIXES = ['/onboarding', '/upgrade', '/sign-up', '/sign-in', '/for-schools']

export function isRecordingAllowed(pathname: string | null): boolean {
  if (!pathname) return false
  if (pathname === '/') return true
  return RECORDING_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`))
}

export default function PostHogRouteRecording() {
  const pathname = usePathname()

  useEffect(() => {
    try {
      if (isRecordingAllowed(pathname)) posthog.startSessionRecording()
      else posthog.stopSessionRecording()
    } catch {
      // analytics never breaks the page
    }
  }, [pathname])

  return null
}
