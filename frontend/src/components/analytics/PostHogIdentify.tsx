'use client'

import { useEffect, useRef } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import posthog from 'posthog-js'
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events'

/** A Clerk account this young counts as "just signed up" on this device. */
export const SIGNUP_WINDOW_MS = 10 * 60 * 1000
export const SIGNUP_TRACKED_KEY = 'chesster_signup_tracked'

type ClerkUserLike = {
  createdAt?: Date | null
  externalAccounts?: Array<{ provider?: string }>
  primaryEmailAddressId?: string | null
  primaryPhoneNumberId?: string | null
}

function signupMethod(user: ClerkUserLike): 'google' | 'email' | 'phone' | 'other' {
  if (user.externalAccounts?.some((a) => (a.provider || '').includes('google'))) return 'google'
  if (user.primaryEmailAddressId) return 'email'
  if (user.primaryPhoneNumberId) return 'phone'
  return 'other'
}

/**
 * Ties PostHog's distinct id to the Clerk user id — and nothing else (no
 * email, name, or phone: many users are kids). Any sign-out path (UserButton,
 * profile page, delete-account) shows up here as userId → null, which resets
 * PostHog so the next person on the device starts anonymous.
 *
 * Also fires the client copy of `user_signed_up` once per device for a
 * brand-new account (`signup_source: 'client'`, carrying this browser
 * session's UTMs/referrer). The Clerk webhook's server copy is authoritative;
 * see the dedupe note in lib/analytics/events.ts.
 */
export default function PostHogIdentify() {
  const { isLoaded, userId } = useAuth()
  const { user } = useUser()
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

  useEffect(() => {
    if (!user || user.id !== userId) return
    const createdAt = user.createdAt?.getTime()
    if (!createdAt || Date.now() - createdAt > SIGNUP_WINDOW_MS) return
    const key = `${SIGNUP_TRACKED_KEY}:${user.id}`
    try {
      if (localStorage.getItem(key)) return
      localStorage.setItem(key, '1')
    } catch {
      return // no storage → can't dedupe; the server event still counts
    }
    track(ANALYTICS_EVENTS.USER_SIGNED_UP, {
      method: signupMethod(user),
      signup_source: 'client',
    })
  }, [user, userId])

  return null
}
