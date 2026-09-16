'use client'

import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '@clerk/nextjs'
import { apiFetch } from '@/lib/api'

export interface CourseProgress {
  courseId: string
  completedLessons: number
  totalLessons: number
  progress: number
}

const EMPTY: Record<string, CourseProgress> = {}

/**
 * Fetches real per-authenticated-user course progress from
 * `GET /api/courses/progress`. Progress is derived per Clerk user on every
 * request, so this works for all current and future users with no migration.
 *
 * Returns an empty map when the user is not signed in.
 */
export function useCourseProgress() {
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const [courseProgress, setCourseProgress] = useState<Record<string, CourseProgress>>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)

  const refetch = useCallback(() => setReloadKey((k) => k + 1), [])

  useEffect(() => {
    if (!isLoaded) return

    if (!isSignedIn) {
      setCourseProgress(EMPTY)
      setLoading(false)
      return
    }

    let cancelled = false

    async function fetchProgress() {
      setLoading(true)
      try {
        const token = await getToken()
        const data = await apiFetch<Record<string, CourseProgress>>(
          `${process.env.NEXT_PUBLIC_API_URL}/api/courses/progress`,
          {
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          }
        )
        if (!cancelled) {
          setCourseProgress(data)
          setError(null)
        }
      } catch (err) {
        // Reset to empty on any failure so the UI never renders stale numbers
        // from a previous successful fetch (mirrors useLessonCompletions).
        if (!cancelled) {
          setCourseProgress(EMPTY)
          setError(err instanceof Error ? err.message : 'Unknown error')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    fetchProgress()

    return () => {
      cancelled = true
    }
  }, [getToken, isLoaded, isSignedIn, reloadKey])

  return { courseProgress, loading, error, refetch }
}
