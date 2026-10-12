'use client'

import { useEffect, useRef } from 'react'
import { useAuth } from '@clerk/nextjs'
import posthog from 'posthog-js'

/**
 * Ties PostHog's distinct id to the Clerk user id — and nothing else (no
 * email, name, or phone: many users are kids). Any sign-out path (UserButton,
 * profile page, delete-account) shows up here as userId → null, which resets
 * PostHog so the next person on the device starts anonymous.
 */
export default function PostHogIdentify() {
  const { isLoaded, userId } = useAuth()
  const prevUserId = useRef<string | null>(null)

  useEffect(() => {
    if (!isLoaded) return
    if (userId) {
      if (userId !== prevUserId.current) posthog.identify(userId)
    } else if (prevUserId.current) {
      posthog.reset()
    }
    prevUserId.current = userId ?? null
  }, [isLoaded, userId])

  return null
}
