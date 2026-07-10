'use client'

import { useUser, useClerk } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { StreakBanner } from '@/components/gamification/StreakBanner'
import { XPDisplay } from '@/components/gamification/XPDisplay'
import LoadingScreen from '@/components/LoadingScreen'
import { useState } from 'react'

export default function ProfilePage() {
  const { user, isLoaded } = useUser()
  const { signOut } = useClerk()
  const router = useRouter()
  const t = useTranslations()

  // Mock gamification data (will be from API later)
  const [userXP] = useState(450)
  const [streakDays] = useState(5)

  // Mock achievements with translation keys
  const achievements = [
    { id: 1, nameKey: 'firstSteps', descKey: 'firstStepsDesc', icon: '🎯', earned: true, xp: 10 },
    { id: 2, nameKey: 'quickLearner', descKey: 'quickLearnerDesc', icon: '📚', earned: true, xp: 25 },
    { id: 3, nameKey: 'onFire', descKey: 'onFireDesc', icon: '🔥', earned: false, xp: 50 },
    { id: 4, nameKey: 'puzzleMaster', descKey: 'puzzleMasterDesc', icon: '🧩', earned: false, xp: 100 },
    { id: 5, nameKey: 'knightRank', descKey: 'knightRankDesc', icon: '♞', earned: true, xp: 50 },
    { id: 6, nameKey: 'courseComplete', descKey: 'courseCompleteDesc', icon: '🎓', earned: false, xp: 100 },
  ]

  // Mock stats
  const stats = {
    lessonsCompleted: 12,
    puzzlesSolved: 28,
    coursesCompleted: 0,
    totalPracticeMinutes: 145,
  }

  const handleSignOut = async () => {
    await signOut()
    router.push('/')
  }

  if (!isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  if (!user) {
    router.push('/sign-in')
    return null
  }

  return (
    <div className="min-h-screen bg-gray-50 animate-page-enter">
      {/* Profile Header */}
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center gap-4">
            <div className="w-20 h-20 rounded-full bg-white/20 flex items-center justify-center overflow-hidden">
              {user.imageUrl ? (
                <img src={user.imageUrl} alt={user.firstName || 'Profile'} className="w-full h-full object-cover" />
              ) : (
                <span className="text-4xl">👤</span>
              )}
            </div>
            <div className="flex-1">
              <h1 className="text-2xl font-bold">{user.firstName || 'Chess Player'}</h1>
              <p className="text-purple-200">{user.emailAddresses[0]?.emailAddress}</p>
              <div className="flex items-center gap-3 mt-2">
                <XPDisplay xp={userXP} size="sm" />
                <span className="text-purple-200">•</span>
                <span className="flex items-center gap-1">
                  <span className="text-orange-400">🔥</span>
                  <span>{streakDays} {t('gamification.dayStreak')}</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6 space-y-6">
        {/* Streak */}
        <StreakBanner
          streakDays={streakDays}
          lastActivityDate={new Date().toISOString()}
          showCalendar
        />

        {/* Stats Grid */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('profile.yourStats')}</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="bg-purple-50 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-purple-600">{stats.lessonsCompleted}</div>
              <div className="text-sm text-gray-600">{t('profile.lessonsCompleted')}</div>
            </div>
            <div className="bg-amber-50 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-amber-600">{stats.puzzlesSolved}</div>
              <div className="text-sm text-gray-600">{t('profile.puzzlesSolved')}</div>
            </div>
            <div className="bg-green-50 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-green-600">{stats.coursesCompleted}</div>
              <div className="text-sm text-gray-600">{t('profile.coursesCompleted')}</div>
            </div>
            <div className="bg-blue-50 rounded-xl p-4 text-center">
              <div className="text-3xl font-bold text-blue-600">{stats.totalPracticeMinutes}</div>
              <div className="text-sm text-gray-600">{t('profile.minutesPracticed')}</div>
            </div>
          </div>
        </div>

        {/* Achievements */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('profile.achievements')}</h2>
          <div className="grid grid-cols-3 gap-3">
            {achievements.map((achievement) => (
              <div
                key={achievement.id}
                className={`p-3 rounded-xl text-center transition-all ${
                  achievement.earned
                    ? 'bg-amber-50 border-2 border-amber-200'
                    : 'bg-gray-100 opacity-50'
                }`}
              >
                <div className={`text-3xl mb-1 ${achievement.earned ? '' : 'grayscale'}`}>
                  {achievement.icon}
                </div>
                <div className={`text-xs font-medium ${achievement.earned ? 'text-gray-900' : 'text-gray-500'}`}>
                  {t(`profile.achievementsList.${achievement.nameKey}`)}
                </div>
                {achievement.earned && (
                  <div className="text-xs text-amber-600 mt-1">+{achievement.xp} {t('gamification.xp')}</div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Account Actions */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">{t('profile.account')}</h2>
          <div className="space-y-3">
            <button
              onClick={() => router.push('/settings')}
              className="w-full flex items-center justify-between p-3 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl">♞</span>
                <span className="font-medium text-gray-900">Board & App Settings</span>
              </div>
              <span className="text-gray-400">→</span>
            </button>

            <button
              onClick={() => router.push('/user-profile')}
              className="w-full flex items-center justify-between p-3 bg-gray-50 rounded-xl hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl">⚙️</span>
                <span className="font-medium text-gray-900">{t('profile.accountSettings')}</span>
              </div>
              <span className="text-gray-400">→</span>
            </button>

            <button
              onClick={handleSignOut}
              className="w-full flex items-center justify-between p-3 bg-red-50 rounded-xl hover:bg-red-100 transition-colors"
            >
              <div className="flex items-center gap-3">
                <span className="text-xl">🚪</span>
                <span className="font-medium text-red-600">{t('profile.signOut')}</span>
              </div>
              <span className="text-red-400">→</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
