'use client'

import { useEffect, useState, useMemo } from 'react'
import { useAuth, useUser } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useTranslations } from 'next-intl'
import LoadingScreen from '@/components/LoadingScreen'
import { StreakBanner, StreakMini } from '@/components/gamification/StreakBanner'
import { XPDisplay } from '@/components/gamification/XPDisplay'
import { LevelBadge, getLevelFromXp } from '@/components/gamification/LevelBadge'
import { LessonPath } from '@/components/gamification/LessonPath'
import { SpeechBubble } from '@/components/mascot/SpeechBubble'

interface Course {
  id: string
  title: string
  description: string
  level: 'beginner' | 'intermediate' | 'advanced'
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

export default function DashboardPage() {
  const { getToken, isSignedIn, isLoaded } = useAuth()
  const { user } = useUser()
  const router = useRouter()
  const t = useTranslations()
  const [courses, setCourses] = useState<Course[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Gamification state (mock data for now - will be from API later)
  const [userXP, setUserXP] = useState(450)
  const [streakDays, setStreakDays] = useState(5)
  const [courseProgress, setCourseProgress] = useState<Record<string, CourseProgress>>({})

  useEffect(() => {
    async function fetchCourses() {
      try {
        const token = await getToken()
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/courses`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        })

        if (!response.ok) {
          throw new Error('Failed to fetch courses')
        }

        const data = await response.json()
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
      } finally {
        setLoading(false)
      }
    }

    fetchCourses()
  }, [getToken])

  // Transform courses for LessonPath component
  const lessonPathCourses = useMemo(() => {
    return courses
      .sort((a, b) => a.order_index - b.order_index)
      .map((course, index) => {
        const progress = courseProgress[course.id]
        const isLocked = index > 0 && (courseProgress[courses[index - 1]?.id]?.progress || 0) < 100

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
      id: 'puzzle',
      title: t('dashboard.chessPuzzles'),
      description: t('dashboard.chessPuzzlesDesc'),
      icon: '🧩',
      href: '/puzzle',
      gradient: 'from-purple-500 to-purple-600'
    },
    {
      id: 'debut',
      title: t('dashboard.debut'),
      description: t('dashboard.debutDesc'),
      icon: '📖',
      href: '/debut',
      gradient: 'from-orange-500 to-orange-600'
    }
  ]

  const getLevelTranslation = (level: string) => {
    const levels: Record<string, string> = {
      'beginner': t('dashboard.levels.beginner'),
      'intermediate': t('dashboard.levels.intermediate'),
      'advanced': t('dashboard.levels.advanced')
    }
    return levels[level] || level
  }

  const greeting = useMemo(() => {
    const hour = new Date().getHours()
    const name = user?.firstName || t('common.chesster')

    if (hour < 12) return `${t('mascot.greeting.morning')}, ${name}!`
    if (hour < 18) return `${t('mascot.greeting.afternoon')}, ${name}!`
    return `${t('mascot.greeting.evening')}, ${name}!`
  }, [user?.firstName, t])

  const mascotMessage = useMemo(() => {
    if (streakDays >= 7) return t('mascot.messages.onFire')
    if (streakDays >= 3) return t('mascot.messages.greatConsistency')
    if (currentCourse?.progress === 0) return t('mascot.messages.readyToStart')
    return t('mascot.messages.welcomeBack')
  }, [streakDays, currentCourse?.progress, t])

  if (loading || !isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header with streak and XP */}
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-4">
              <StreakMini streakDays={streakDays} />
              <XPDisplay xp={userXP} size="md" />
            </div>
            <LevelBadge xp={userXP} size="sm" showName={false} />
          </div>

          <h1 className="text-2xl font-bold">{greeting}</h1>
          <p className="text-purple-200 mt-1">
            {t(`gamification.levels.${getLevelFromXp(userXP)}`)} {t('gamification.level')} • {userXP.toLocaleString()} {t('gamification.xp')}
          </p>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6">
        {/* Mascot greeting */}
        <div className="mb-6">
          <SpeechBubble mood={streakDays >= 3 ? 'celebrating' : 'happy'} mascotSize="sm">
            {mascotMessage}
          </SpeechBubble>
        </div>

        {/* Continue Learning Card */}
        {currentCourse && (
          <div className="mb-8">
            <Link
              href={`/learn/${currentCourse.slug}`}
              className="block bg-white rounded-2xl shadow-lg p-6 border-2 border-purple-200 hover:border-purple-400 transition-all hover:shadow-xl"
            >
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-purple-600 uppercase tracking-wide">
                  {t('dashboard.continueLearning')}
                </span>
                <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                  currentCourse.level === 'beginner' ? 'bg-green-100 text-green-700' :
                  currentCourse.level === 'intermediate' ? 'bg-amber-100 text-amber-700' :
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
          </div>
        )}

        {/* Quick Actions */}
        <div className="mb-8">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('dashboard.quickActions')}</h2>
          <div className="grid grid-cols-3 gap-3">
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
        <div className="mb-8">
          <StreakBanner
            streakDays={streakDays}
            lastActivityDate={new Date().toISOString()}
            showCalendar
          />
        </div>

        {/* Learning Path */}
        <div className="mb-8">
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
        <div className="bg-white rounded-2xl shadow-md p-6 mb-8">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('dashboard.todaysGoals')}</h2>
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 bg-gray-50 rounded-xl">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 bg-green-100 rounded-full flex items-center justify-center">
                  {streakDays > 0 ? '✅' : '⏳'}
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
