'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/nextjs'
import { apiFetch } from '@/lib/api'

export interface LessonCompletions {
  total_completions: number
  completion_dates: string[]
}

const EMPTY: LessonCompletions = { total_completions: 0, completion_dates: [] }

/**
 * Fetches the authenticated user's raw lesson-completion signal from
 * `GET /api/gamification/derived-profile`. Non-linked Chesster users turn this
 * into derived XP / rank / streak (see `lib/gamification/derived.ts`).
 *
 * Returns zeros when signed out or on error, so callers can compute a safe
 * derived profile unconditionally.
 */
export function useLessonCompletions() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const [completions, setCompletions] = useState<LessonCompletions>(EMPTY)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      setCompletions(EMPTY)
      setLoading(false)
      return
    }

    let cancelled = false

    async function fetchCompletions() {
      setLoading(true)
      try {
        const token = await getToken()
        const data = await apiFetch<LessonCompletions>(
          `${process.env.NEXT_PUBLIC_API_URL}/api/gamification/derived-profile`,
          {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          }
        )
        if (!cancelled) setCompletions(data)
      } catch {
        if (!cancelled) setCompletions(EMPTY)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchCompletions()

    return () => {
      cancelled = true
    }
  }, [getToken, isLoaded, isSignedIn])

  return { completions, loading }
}
