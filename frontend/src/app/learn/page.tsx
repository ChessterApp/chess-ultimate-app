'use client'

import { useEffect, useState, useMemo } from 'react'
import { useAuth, SignInButton } from '@clerk/nextjs'
import { useTranslations, useLocale } from 'next-intl'
import Image from 'next/image'
import LoadingScreen from '@/components/LoadingScreen'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'
import { LessonPath } from '@/components/gamification/LessonPath'
import { LevelProgressCard } from '@/components/gamification/LevelBadge'
import { SpeechBubble } from '@/components/mascot/SpeechBubble'

interface Course {
  id: string
  title: string
  description: string
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert' | 'legendary'
  order_index: number
  slug?: string
}

interface CourseProgress {
  courseId: string
  completedLessons: number
  totalLessons: number
  progress: number
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

export default function LearnPage() {
  const { getToken, isSignedIn, isLoaded } = useAuth()
  const t = useTranslations()
  const locale = useLocale()
  const { showToast } = useToast()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Gamification state (mock data for now)
  const [userXP] = useState(450)
  const [courseProgress, setCourseProgress] = useState<Record<string, CourseProgress>>({})

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

        // Mock progress data - will be replaced with real API
        const mockProgress: Record<string, CourseProgress> = {}
        data.forEach((course: Course, index: number) => {
          mockProgress[course.id] = {
            courseId: course.id,
            completedLessons: index === 0 ? 3 : 0,
            totalLessons: 10,
            progress: index === 0 ? 30 : 0
          }
        })
        setCourseProgress(mockProgress)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
        if (err instanceof ApiError) {
          if (err.status === 429) {
            showToast('Too many requests — please slow down', 'error')
          } else if (err.status === 408) {
            showToast('Request timed out — try again', 'error')
          } else if (err.status === 0) {
            showToast('Network error — check your connection', 'error')
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
    return courses
      .sort((a, b) => a.order_index - b.order_index)
      .map((course, index) => {
        const progress = courseProgress[course.id]
        const isLocked = false

        return {
          id: course.id,
          slug: course.slug || generateSlug(course.title),
          title: course.title,
          level: course.level,
          progress: progress?.progress || 0,
          isLocked,
          lessons: [] // Lessons loaded on course page
        }
      })
  }, [courses, courseProgress])

  // Group courses by level
  const coursesByLevel = useMemo(() => {
    const grouped = {
      beginner: lessonPathCourses.filter(c => c.level === 'beginner'),
      intermediate: lessonPathCourses.filter(c => c.level === 'intermediate'),
      advanced: lessonPathCourses.filter(c => c.level === 'advanced'),
      master: lessonPathCourses.filter(c => c.level === 'master'),
      expert: lessonPathCourses.filter(c => c.level === 'expert'),
      legendary: lessonPathCourses.filter(c => c.level === 'legendary'),
    }
    return grouped
  }, [lessonPathCourses])

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
        <div className="container mx-auto px-4 py-6">
          <h1 className="text-2xl font-bold">{t('learn.title')}</h1>
          <p className="text-purple-200 mt-1">{t('learn.subtitle')}</p>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6">
        {/* Mascot welcome */}
        <div className="mb-6">
          <SpeechBubble mood="encouraging" mascotSize="sm">
            {t('mascot.messages.followPath')}
          </SpeechBubble>
        </div>

        {/* Level Progress */}
        <div className="mb-8">
          <LevelProgressCard xp={userXP} />
        </div>

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl mb-6">
            {error}
          </div>
        )}

        {/* Course Path */}
        {lessonPathCourses.length > 0 ? (
          <div className="space-y-8">
            {/* Beginner Section */}
            {coursesByLevel.beginner.length > 0 && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-green-500 rounded-full"></span>
                  <h2 className="text-lg font-bold text-gray-900">{t('learn.beginner')}</h2>
                  <span className="text-sm text-gray-500">
                    ({coursesByLevel.beginner.filter(c => c.progress === 100).length}/{coursesByLevel.beginner.length} {t('learn.complete')})
                  </span>
                </div>
                <LessonPath courses={coursesByLevel.beginner} />
              </div>
            )}

            {/* Intermediate Section */}
            {coursesByLevel.intermediate.length > 0 && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-amber-500 rounded-full"></span>
                  <h2 className="text-lg font-bold text-gray-900">{t('learn.intermediate')}</h2>
                  <span className="text-sm text-gray-500">
                    ({coursesByLevel.intermediate.filter(c => c.progress === 100).length}/{coursesByLevel.intermediate.length} {t('learn.complete')})
                  </span>
                </div>
                <LessonPath courses={coursesByLevel.intermediate} />
              </div>
            )}

            {/* Advanced Section */}
            {coursesByLevel.advanced.length > 0 && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-red-500 rounded-full"></span>
                  <h2 className="text-lg font-bold text-gray-900">{t('learn.advanced')}</h2>
                  <span className="text-sm text-gray-500">
                    ({coursesByLevel.advanced.filter(c => c.progress === 100).length}/{coursesByLevel.advanced.length} {t('learn.complete')})
                  </span>
                </div>
                <LessonPath courses={coursesByLevel.advanced} />
              </div>
            )}

            {/* Master Section */}
            {coursesByLevel.master.length > 0 && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-purple-500 rounded-full"></span>
                  <h2 className="text-lg font-bold text-gray-900">{t('learn.master')}</h2>
                  <span className="text-sm text-gray-500">
                    ({coursesByLevel.master.filter(c => c.progress === 100).length}/{coursesByLevel.master.length} {t('learn.complete')})
                  </span>
                </div>
                <LessonPath courses={coursesByLevel.master} />
              </div>
            )}

            {/* Expert Section */}
            {coursesByLevel.expert.length > 0 && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-amber-500 rounded-full"></span>
                  <h2 className="text-lg font-bold text-gray-900">{t('learn.expert')}</h2>
                  <span className="text-sm text-gray-500">
                    ({coursesByLevel.expert.filter(c => c.progress === 100).length}/{coursesByLevel.expert.length} {t('learn.complete')})
                  </span>
                </div>
                <LessonPath courses={coursesByLevel.expert} />
              </div>
            )}

            {/* Legendary Section */}
            {coursesByLevel.legendary.length > 0 && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center gap-2 mb-4">
                  <span className="w-3 h-3 bg-rose-500 rounded-full"></span>
                  <h2 className="text-lg font-bold text-gray-900">{t('learn.legendary')}</h2>
                  <span className="text-sm text-gray-500">
                    ({coursesByLevel.legendary.filter(c => c.progress === 100).length}/{coursesByLevel.legendary.length} {t('learn.complete')})
                  </span>
                </div>
                <LessonPath courses={coursesByLevel.legendary} />
              </div>
            )}
          </div>
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
