'use client'

import { useEffect, useState, useMemo } from 'react'
import { useAuth, SignInButton } from '@clerk/nextjs'
import { useTranslations, useLocale } from 'next-intl'
import { useRouter } from 'next/navigation'
import Image from 'next/image'
import LoadingScreen from '@/components/LoadingScreen'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'
import { LessonPath } from '@/components/gamification/LessonPath'
import { SpeechBubble } from '@/components/mascot/SpeechBubble'
import { useCourseProgress } from '@/hooks/useCourseProgress'
import { computeLockStates, resolveRestrictedCeiling } from '@/lib/learn-gating'
import { getAccessPolicy, type AccessPolicy } from '@/lib/access-policy'

interface Course {
  id: string
  title: string
  description: string
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert' | 'legendary' | 'grandmaster'
  order_index: number
  slug?: string
}

// Generate slug from title if not available
function generateSlug(title: string): string {
  return title
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

export default function LearnClient({
  ceLevelFloor,
  policy = getAccessPolicy(null),
}: {
  ceLevelFloor?: number
  policy?: AccessPolicy
}) {
  const { getToken, isSignedIn, isLoaded } = useAuth()
  const t = useTranslations()
  const locale = useLocale()
  const router = useRouter()
  const { showToast } = useToast()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Real per-user course progress (derived from user_progress on the backend).
  const { courseProgress } = useCourseProgress()

  useEffect(() => {
    async function fetchCourses() {
      if (!isLoaded) return

      if (!isSignedIn) {
        setLoading(false)
        return
      }

      try {
        const token = await getToken()
        const data = await apiFetch<Course[]>(`${process.env.NEXT_PUBLIC_API_URL}/api/courses?locale=${locale}&_v=${Date.now()}`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        setCourses(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
        if (err instanceof ApiError) {
          if (err.status === 429) {
            showToast(t('learn.errors.tooManyRequests'), 'error')
          } else if (err.status === 408) {
            showToast(t('learn.errors.requestTimeout'), 'error')
          } else if (err.status === 0) {
            showToast(t('learn.errors.networkError'), 'error')
          }
        }
      } finally {
        setLoading(false)
      }
    }

    fetchCourses()
  }, [getToken, isLoaded, isSignedIn, showToast, locale])

  // Transform courses for LessonPath component
  const lessonPathCourses = useMemo(() => {
    const sortedCourses = [...courses].sort((a, b) => a.order_index - b.order_index)
    const gatingCourses = sortedCourses.map((c) => ({ id: c.id, order_index: c.order_index }))

    // Restricted (frozen/expired) members are capped at their current level.
    const restrictedCeiling = resolveRestrictedCeiling(policy, gatingCourses, courseProgress)

    const lockStates = computeLockStates(gatingCourses, courseProgress, ceLevelFloor, restrictedCeiling)
    // Without the ceiling — anything locked here but unlocked below was locked
    // *by the restriction*, so it gets the distinct "membership" treatment.
    const baseLockStates = computeLockStates(gatingCourses, courseProgress, ceLevelFloor)

    return sortedCourses
      .map((course) => {
        const progress = courseProgress[course.id]
        const isLocked = lockStates[course.id] ?? false
        const isCeilingLocked = isLocked && !(baseLockStates[course.id] ?? false)

        return {
          id: course.id,
          slug: course.slug || generateSlug(course.title),
          title: course.title,
          level: course.level,
          progress: progress?.progress || 0,
          isLocked,
          isCeilingLocked,
          lessons: [] // Lessons loaded on course page
        }
      })
  }, [courses, courseProgress, ceLevelFloor, policy])

  if (loading || !isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  if (!isSignedIn) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md text-center">
          <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={64} height={64} className="w-16 h-16 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-gray-900 mb-2">{t('learn.startJourney')}</h1>
          <p className="text-gray-600 mb-6">
            {t('learn.signInPrompt')}
          </p>
          <SignInButton mode="modal">
            <button className="w-full bg-purple-600 hover:bg-purple-700 text-white font-semibold py-3 px-6 rounded-xl transition-colors">
              {t('learn.signInToLearn')}
            </button>
          </SignInButton>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 animate-page-enter">
      {/* Header */}
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="max-w-[600px] mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold">{t('learn.title')}</h1>
          <p className="text-purple-200 mt-1">{t('learn.subtitle')}</p>
        </div>
      </div>

      <div className="max-w-[600px] mx-auto px-4 py-6">
        {/* Mascot welcome */}
        <div className="mb-6">
          <SpeechBubble mood="encouraging" mascotSize="sm">
            {t('mascot.messages.followPath')}
          </SpeechBubble>
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl mb-6">
            {error}
          </div>
        )}

        {/* Single continuous course path */}
        {lessonPathCourses.length > 0 ? (
          <LessonPath
            courses={lessonPathCourses}
            ceilingHint={t('access.learnCeiling.hint')}
            onCeilingLockClick={() =>
              router.replace('/learn?locked=level', { scroll: false })
            }
          />
        ) : (
          <div className="text-center text-gray-500 bg-white rounded-2xl p-8">
            <p className="text-lg">{t('dashboard.noCourses')}</p>
            <p className="mt-2 text-sm">{t('dashboard.checkBack')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
