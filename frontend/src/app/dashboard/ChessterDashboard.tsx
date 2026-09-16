'use client'

import { useEffect, useState, useMemo } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import LoadingScreen from '@/components/LoadingScreen'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'
import { useBackendHealth } from '@/hooks/useBackendHealth'
import { StreakBanner, StreakMini } from '@/components/gamification/StreakBanner'
import { XPDisplay } from '@/components/gamification/XPDisplay'
import { LessonPath } from '@/components/gamification/LessonPath'
import { SpeechBubble } from '@/components/mascot/SpeechBubble'
import TournamentCtaBanner from '@/components/empire/TournamentCtaBanner'
import { useCourseProgress } from '@/hooks/useCourseProgress'
import { useLessonCompletions } from '@/hooks/useLessonCompletions'
import { computeLockStates } from '@/lib/learn-gating'
import type { GamificationProfile } from '@/lib/gamification/profile'
import { deriveProfile, computeDailyStreak } from '@/lib/gamification/derived'

interface Course {
  id: string
  title: string
  description: string
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert'
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

export default function ChessterDashboard({
  showTournamentCta = false,
}: {
  /**
   * Render the Empire tournament CTA banner above the dashboard. Set only on
   * the chess-empire tenant host (frozen / revoked / no-membership students),
   * where the generic dashboard is the surface they land on.
   */
  showTournamentCta?: boolean
} = {}) {
  const { getToken, isSignedIn, isLoaded } = useAuth()
  const { user } = useUser()
  const router = useRouter()
  const t = useTranslations()
  const { showToast } = useToast()
  const backendHealthy = useBackendHealth()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Gate time-of-day / date-dependent output so the SSR render and the FIRST
  // client render are byte-identical (React #418). `new Date()` differs between
  // the UTC server and the user's local timezone, so anything derived from the
  // current time must only be computed after mount.
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    setMounted(true)
  }, [])

  // Real gamification profile (XP + tournament-week streak), fed like EmpireHomePage.
  const [profile, setProfile] = useState<GamificationProfile | null>(null)

  // Real per-user course progress (derived from user_progress on the backend).
  const {
    courseProgress,
    loading: progressLoading,
    error: progressError,
    refetch: refetchProgress,
  } = useCourseProgress()

  // Raw lesson-completion signal → derived XP/rank/streak for non-linked users.
  const { completions } = useLessonCompletions()

  useEffect(() => {
    async function fetchCourses() {
      try {
        const token = await getToken()
        const data = await apiFetch<Course[]>(`${process.env.NEXT_PUBLIC_API_URL}/api/courses`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })
        setCourses(data)
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
  }, [getToken, showToast])

  // Real XP + streak from the gamification profile (§9). Unlinked/non-CE users
  // resolve to a hidden profile — we simply show zeros rather than mock values.
  useEffect(() => {
    if (!isSignedIn) return
    let cancelled = false
    fetch('/api/gamification/profile')
      .then((r) => (r.ok ? r.json() : null))
      .then((data: GamificationProfile | null) => {
        if (!cancelled) setProfile(data)
      })
      .catch(() => {
        if (!cancelled) setProfile(null)
      })
    return () => {
      cancelled = true
    }
  }, [isSignedIn])

  // Non-linked users derive XP + rank + a DAILY streak from lesson completions;
  // linked users keep their tournament-driven weekly economy (unchanged).
  const derived = useMemo(
    () => deriveProfile(completions.total_completions),
    [completions.total_completions],
  )
  // The daily streak depends on "today", which is timezone-relative — keep it at
  // 0 until mounted so server and first client render match, then fill it in.
  const derivedStreak = useMemo(
    () => (mounted ? computeDailyStreak(completions.completion_dates, new Date()) : 0),
    [completions.completion_dates, mounted],
  )

  const linked = profile?.linked === true
  const userXP = linked ? profile!.xp : derived.xp
  const streakCount = linked ? profile!.streak.current_weeks : derivedStreak
  const streakUnit: 'weeks' | 'days' = linked ? 'weeks' : 'days'
  const nextMilestone = linked ? profile!.streak.next_milestone : null

  // Transform courses for LessonPath component
  const lessonPathCourses = useMemo(() => {
    const sortedCourses = [...courses].sort((a, b) => a.order_index - b.order_index)
    // No ceLevelFloor here: ChessterDashboard is only shown to non-CE or
    // unlinked users; verified CE students get EmpireHomePage (no LessonPath).
    const lockStates = computeLockStates(
      sortedCourses.map((c) => ({ id: c.id, order_index: c.order_index })),
      courseProgress
    )
    return sortedCourses
      .map((course) => {
        const progress = courseProgress[course.id]
        const isLocked = lockStates[course.id] ?? false

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

  // Find current/next course to continue
  const currentCourse = useMemo(() => {
    return lessonPathCourses.find(c => !c.isLocked && c.progress < 100) || lessonPathCourses[0]
  }, [lessonPathCourses])

  const analysisTools = [
    {
      id: 'position',
      title: t('dashboard.positionAnalysis'),
      description: t('dashboard.positionAnalysisDesc'),
      icon: '♞',
      href: '/position',
      gradient: 'from-blue-500 to-blue-600'
    },
    {
      id: 'coach',
      title: 'AI Coach',
      description: 'Interactive coaching with board control',
      icon: '🎓',
      href: '/coach',
      gradient: 'from-indigo-500 to-indigo-600'
    },
    {
      id: 'database',
      title: t('dashboard.database'),
      description: t('dashboard.databaseDesc'),
      icon: '📖',
      href: '/database',
      gradient: 'from-orange-500 to-orange-600'
    },
    {
      id: 'play',
      title: 'Play vs Maia',
      description: 'Play against human-like AI',
      icon: '🤖',
      href: '/play',
      gradient: 'from-green-500 to-green-600'
    }
  ]

  const getLevelTranslation = (level: string) => {
    const levels: Record<string, string> = {
      'beginner': t('dashboard.levels.beginner'),
      'intermediate': t('dashboard.levels.intermediate'),
      'advanced': t('dashboard.levels.advanced'),
      'master': t('dashboard.levels.master'),
      'expert': t('dashboard.levels.expert')
    }
    return levels[level] || level
  }

  const greeting = useMemo(() => {
    const name = user?.firstName || t('common.chesster')

    // Before mount, render a stable, time-agnostic greeting so SSR and the first
    // client render are identical; swap to the time-aware word once mounted.
    if (!mounted) return `${name}!`

    const hour = new Date().getHours()
    if (hour < 12) return `${t('mascot.greeting.morning')}, ${name}!`
    if (hour < 18) return `${t('mascot.greeting.afternoon')}, ${name}!`
    return `${t('mascot.greeting.evening')}, ${name}!`
  }, [user?.firstName, t, mounted])

  const mascotMessage = useMemo(() => {
    if (streakCount >= 7) return t('mascot.messages.onFire')
    if (streakCount >= 3) return t('mascot.messages.greatConsistency')
    if (currentCourse?.progress === 0) return t('mascot.messages.readyToStart')
    return t('mascot.messages.welcomeBack')
  }, [streakCount, currentCourse?.progress, t])

  if (loading || !isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  return (
    <div className="min-h-screen bg-gray-50 animate-page-enter">
      {/* Header with streak and XP */}
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <StreakMini streakDays={streakCount} />
              <XPDisplay xp={userXP} size="md" />
            </div>
          </div>

          <h1 className="text-2xl font-bold">{greeting}</h1>
          <p className="text-purple-200 mt-1">
            {userXP.toLocaleString()} {t('gamification.xp')}
          </p>
        </div>
      </div>

      {showTournamentCta && (
        <div className="container mx-auto px-4 pt-6">
          <TournamentCtaBanner />
        </div>
      )}

      <div className="container mx-auto px-4 py-6 md:grid md:grid-cols-2 lg:grid-cols-3 md:gap-6 md:items-start">
        {backendHealthy === false && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 mb-4 text-center md:col-span-2 lg:col-span-3">
            <p className="text-amber-700 text-sm">
              ♞ Some features may be temporarily unavailable. We&apos;re working on it!
            </p>
          </div>
        )}

        {/* Mascot greeting */}
        <div className="mb-6 md:col-span-2 lg:col-span-3">
          <SpeechBubble mood={streakCount >= 3 ? 'celebrating' : 'happy'} mascotSize="sm">
            {mascotMessage}
          </SpeechBubble>
        </div>

        {/* Continue Learning Card. Progress is fetched separately from the course
            list, so never render numbers from a failed/pending fetch: show a
            skeleton while loading and a retry state on error instead of stale 0s. */}
        {currentCourse && (
          <div className="mb-8 md:col-span-2 lg:col-span-2" data-testid="continue-learning">
            {progressLoading ? (
              <div
                className="block bg-white rounded-2xl shadow-md p-4 border-2 border-purple-200"
                data-testid="continue-learning-loading"
                aria-busy="true"
              >
                <div className="animate-pulse">
                  <div className="flex items-center justify-between mb-3">
                    <div className="h-4 w-32 bg-gray-200 rounded" />
                    <div className="h-5 w-16 bg-gray-200 rounded-full" />
                  </div>
                  <div className="h-6 w-48 bg-gray-200 rounded mb-3" />
                  <div className="h-3 w-full bg-gray-200 rounded-full" />
                  <div className="mt-4 h-4 w-40 bg-gray-200 rounded" />
                </div>
              </div>
            ) : progressError ? (
              <div
                className="block bg-white rounded-2xl shadow-md p-4 border-2 border-purple-200"
                data-testid="continue-learning-error"
              >
                <span className="text-sm font-medium text-purple-600 uppercase tracking-wide">
                  {t('dashboard.continueLearning')}
                </span>
                <p className="mt-2 text-sm text-gray-600">{t('dashboard.progressLoadError')}</p>
                <button
                  type="button"
                  onClick={refetchProgress}
                  className="mt-3 px-4 py-2 rounded-lg bg-purple-600 text-white text-sm font-semibold hover:bg-purple-700 transition-colors active:scale-95"
                >
                  {t('dashboard.retry')}
                </button>
              </div>
            ) : (
              <Link
                href="/learn"
                className="block bg-white rounded-2xl shadow-md p-4 border-2 border-purple-200 hover:border-purple-400 transition-all hover:shadow-lg"
              >
                <div className="flex items-center justify-between mb-3">
                  <span className="text-sm font-medium text-purple-600 uppercase tracking-wide">
                    {t('dashboard.continueLearning')}
                  </span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                    currentCourse.level === 'beginner' ? 'bg-green-100 text-green-700' :
                    currentCourse.level === 'intermediate' ? 'bg-amber-100 text-amber-700' :
                    currentCourse.level === 'master' ? 'bg-purple-100 text-purple-700' :
                    'bg-red-100 text-red-700'
                  }`}>
                    {getLevelTranslation(currentCourse.level)}
                  </span>
                </div>

                <h2 className="text-xl font-bold text-gray-900 mb-2">{currentCourse.title}</h2>

                <div className="flex items-center gap-3">
                  <div className="flex-1 h-3 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-purple-500 to-purple-600 rounded-full transition-all duration-500"
                      style={{ width: `${currentCourse.progress}%` }}
                    />
                  </div>
                  <span className="text-sm font-semibold text-gray-600">
                    {Math.round(currentCourse.progress)}%
                  </span>
                </div>

                <div className="mt-4 flex items-center justify-between">
                  <span className="text-sm text-gray-500">
                    {courseProgress[currentCourse.id]?.completedLessons || 0} / {courseProgress[currentCourse.id]?.totalLessons || 0} {t('dashboard.lessonsCompleted')}
                  </span>
                  <span className="text-purple-600 font-semibold flex items-center gap-1">
                    {t('dashboard.continue')} →
                  </span>
                </div>
              </Link>
            )}
          </div>
        )}

        {/* Quick Actions */}
        <div className="mb-8 md:col-span-1 lg:col-span-1">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('dashboard.quickActions')}</h2>
          <div className="grid grid-cols-2 md:grid-cols-1 gap-3 stagger-children">
            {analysisTools.map((tool) => (
              <Link
                key={tool.id}
                href={tool.href}
                className={`bg-gradient-to-br ${tool.gradient} text-white rounded-xl p-4 text-center hover:opacity-90 transition-opacity active:scale-95`}
              >
                <div className="text-3xl mb-2">{tool.icon}</div>
                <div className="text-sm font-medium leading-tight">{tool.title}</div>
              </Link>
            ))}
          </div>
        </div>

        {/* Streak Banner (expandable) */}
        <div className="mb-8 md:col-span-1 lg:col-span-1">
          <StreakBanner
            streakDays={streakCount}
            unit={streakUnit}
            nextMilestone={nextMilestone}
          />
        </div>

        {/* Learning Path */}
        <div className="mb-8 md:col-span-2 lg:col-span-2">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('dashboard.learningJourney')}</h2>

          {error && (
            <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-xl mb-6">
              {t('dashboard.errorLoading')}: {error}
            </div>
          )}

          {lessonPathCourses.length > 0 ? (
            <div className="bg-white rounded-2xl shadow-md p-6">
              <LessonPath courses={lessonPathCourses} />
            </div>
          ) : (
            <div className="text-center text-gray-500 bg-white rounded-2xl p-8">
              <p className="text-lg">{t('dashboard.noCourses')}</p>
              <p className="mt-2 text-sm">{t('dashboard.checkBack')}</p>
            </div>
          )}
        </div>

        {/* Daily Goals / Achievements teaser */}
        <div className="bg-white rounded-2xl shadow-md p-6 mb-8 md:col-span-2 lg:col-span-3">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('dashboard.todaysGoals')}</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                  {streakCount > 0 ? '✅' : '⏳'}
                </div>
                <div>
                  <div className="font-medium text-gray-900">{t('dashboard.practiceToday')}</div>
                  <div className="text-sm text-gray-500">{t('dashboard.keepStreakAlive')}</div>
                </div>
              </div>
              <span className="text-xs font-medium text-green-600 bg-green-50 px-2 py-1 rounded-full">
                +5 {t('gamification.xp')}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-purple-100 rounded-full flex items-center justify-center">
                  📚
                </div>
                <div>
                  <div className="font-medium text-gray-900">{t('dashboard.completeLesson')}</div>
                  <div className="text-sm text-gray-500">{t('dashboard.learnSomethingNew')}</div>
                </div>
              </div>
              <span className="text-xs font-medium text-purple-600 bg-purple-50 px-2 py-1 rounded-full">
                +10 {t('gamification.xp')}
              </span>
            </div>

            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
                  🧩
                </div>
                <div>
                  <div className="font-medium text-gray-900">{t('dashboard.solvePuzzles')}</div>
                  <div className="text-sm text-gray-500">{t('dashboard.sharpenTactics')}</div>
                </div>
              </div>
              <span className="text-xs font-medium text-amber-600 bg-amber-50 px-2 py-1 rounded-full">
                +15 {t('gamification.xp')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
