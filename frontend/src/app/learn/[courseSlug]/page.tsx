'use client'

import { useEffect, useState, useCallback, useRef } from 'react'
import { useAuth, SignInButton } from '@clerk/nextjs'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { useTranslations, useLocale } from 'next-intl'
import LoadingScreen from '@/components/LoadingScreen'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'
import Breadcrumbs from '@/components/Breadcrumbs'

interface Course {
  id: string
  title: string
  description: string
  level: string
  slug: string
}

interface Module {
  id: string
  title: string
  description: string
  order_index: number
}

interface Lesson {
  id: string
  module_id: string
  title: string
  slug: string
  lesson_type: string
  order_index: number
  requires_lesson_id: string | null
}

interface Progress {
  status: string
  completed_at: string | null
}

interface CourseData {
  course: Course | null
  modules: Module[]
  lessons: Record<string, Lesson[]>
  progress: Record<string, Progress>
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

export default function CoursePage() {
  const params = useParams()
  const courseSlug = params?.courseSlug as string
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const [authError, setAuthError] = useState<string | null>(null)
  const t = useTranslations()
  const locale = useLocale()
  const { showToast } = useToast()

  const [data, setData] = useState<CourseData | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const fetchedRef = useRef<string | null>(null)

  const mutate = useCallback(async () => {
    fetchedRef.current = null
    setError(null)
  }, [])

  useEffect(() => {
    if (!courseSlug || !isLoaded || !isSignedIn) return

    const url = `${process.env.NEXT_PUBLIC_API_URL}/api/learn/${courseSlug}?locale=${locale}`
    if (fetchedRef.current === url && data) return
    fetchedRef.current = url

    let cancelled = false
    setIsLoading(true)

    async function fetchCourse() {
      try {
        const token = await getToken()
        if (!token) throw new Error('No auth token')

        const result = await apiFetch<CourseData>(url, {
          headers: { 'Authorization': `Bearer ${token}` }
        })

        if (!cancelled) {
          setData(result)
          setError(null)
        }
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError) {
          if (e.status === 401) {
            setError(new Error('Session expired'))
            return
          }
          if (e.status === 408) {
            showToast('Request timed out — try again', 'error')
          } else if (e.status === 0) {
            showToast('Network error — check your connection', 'error')
          }
        }
        setError(new Error('Failed to fetch course data'))
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    fetchCourse()
    return () => { cancelled = true }
  }, [courseSlug, isLoaded, isSignedIn, locale, getToken, showToast, data, mutate])

  // Handle auth state changes
  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      setAuthError('Please sign in to access this course')
    } else {
      setAuthError(null)
    }
  }, [isLoaded, isSignedIn])

  const isLessonUnlocked = (lesson: Lesson): boolean => {
    if (!lesson.requires_lesson_id) return true
    const requiredProgress = data?.progress[lesson.requires_lesson_id]
    return requiredProgress?.status === 'completed'
  }

  // Show loading only on initial load (SWR shows stale data while revalidating)
  if (!isLoaded || (isLoading && !data)) {
    return <LoadingScreen isVisible={true} />
  }

  if (authError || !isSignedIn) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-xl text-red-500 mb-4">
            {authError || t('course.signInRequired')}
          </div>
          <SignInButton mode="modal">
            <button className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded transition-colors">
              {t('common.signIn')}
            </button>
          </SignInButton>
          <div className="mt-4">
            <Link href="/learn" className="text-blue-600 hover:underline">
              ← {t('course.backToDashboard')}
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-xl text-red-500 mb-4">
            {error.message === 'Session expired'
              ? t('course.sessionExpired')
              : t('course.loadError')}
          </div>
          <button
            onClick={() => mutate()}
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded transition-colors mr-4"
          >
            {t('course.retry')}
          </button>
          <Link href="/learn" className="text-blue-600 hover:underline">
            ← {t('course.backToDashboard')}
          </Link>
        </div>
      </div>
    )
  }

  if (!data?.course) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-xl text-red-500 mb-4">{t('course.notFound')}</div>
          <Link href="/learn" className="text-blue-600 hover:underline">
            ← {t('course.backToDashboard')}
          </Link>
        </div>
      </div>
    )
  }

  const { course, modules, lessons, progress } = data

  const getLessonTypeLabel = (type: string) => {
    const types: Record<string, string> = {
      'theory': t('course.lessonTypes.theory'),
      'exercise': t('course.lessonTypes.exercise'),
      'puzzle': t('course.lessonTypes.puzzle')
    }
    return types[type] || type
  }

  const getLevelLabel = (level: string) => {
    const levels: Record<string, string> = {
      'beginner': t('dashboard.levels.beginner'),
      'intermediate': t('dashboard.levels.intermediate'),
      'advanced': t('dashboard.levels.advanced'),
      'master': t('dashboard.levels.master'),
      'expert': t('dashboard.levels.expert')
    }
    return levels[level] || level
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <Breadcrumbs />
      <Link href="/learn" className="text-blue-600 hover:underline mb-4 inline-block">
        ← {t('course.backToDashboard')}
      </Link>

      <div className="mb-8">
        <h1 className="text-4xl font-bold mb-2">{course.title}</h1>
        <p className="text-gray-600 dark:text-gray-300 mb-4">{course.description}</p>
        <span className={`px-3 py-1 rounded-full text-sm ${
          course.level === 'beginner' ? 'bg-green-100 text-green-800' :
          course.level === 'intermediate' ? 'bg-yellow-100 text-yellow-800' :
          course.level === 'master' ? 'bg-purple-100 text-purple-800' :
          course.level === 'expert' ? 'bg-amber-100 text-amber-800' :
          'bg-red-100 text-red-800'
        }`}>
          {getLevelLabel(course.level)}
        </span>
      </div>

      <div className="space-y-8">
        {modules.map((module) => (
          <div key={module.id} className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-2xl font-bold mb-2">{module.title}</h2>
            <p className="text-gray-600 dark:text-gray-300 mb-4">{module.description}</p>

            <div className="space-y-3">
              {lessons[module.id]?.map((lesson) => {
                const unlocked = isLessonUnlocked(lesson)
                const lessonProgress = progress[lesson.id]
                const isCompleted = lessonProgress?.status === 'completed'

                return (
                  <div
                    key={lesson.id}
                    className={`flex items-center justify-between p-4 rounded-lg border-2 ${
                      !unlocked
                        ? 'bg-gray-100 dark:bg-gray-700 border-gray-300 dark:border-gray-600 opacity-60'
                        : isCompleted
                        ? 'bg-green-50 dark:bg-green-900 border-green-300 dark:border-green-700'
                        : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-600'
                    }`}
                  >
                    <div className="flex items-center space-x-4">
                      {!unlocked && (
                        <span className="text-2xl">🔒</span>
                      )}
                      {isCompleted && (
                        <span className="text-2xl">✅</span>
                      )}
                      <div>
                        <h3 className="font-semibold">{lesson.title}</h3>
                        <span className={`text-sm px-2 py-1 rounded ${
                          lesson.lesson_type === 'theory'
                            ? 'bg-blue-100 text-blue-800'
                            : lesson.lesson_type === 'exercise'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-purple-100 text-purple-800'
                        }`}>
                          {getLessonTypeLabel(lesson.lesson_type)}
                        </span>
                      </div>
                    </div>

                    {unlocked ? (
                      <Link
                        href={`/learn/${courseSlug}/${lesson.slug || generateSlug(lesson.title)}`}
                        className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded transition-colors"
                      >
                        {isCompleted ? t('course.review') : t('course.start')}
                      </Link>
                    ) : (
                      <span className="text-gray-500 text-sm">
                        {t('course.completePreviousToUnlock')}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        ))}
      </div>

      {modules.length === 0 && (
        <div className="text-center text-gray-500 mt-12">
          <p className="text-xl">{t('course.noModules')}</p>
        </div>
      )}
    </div>
  )
}
