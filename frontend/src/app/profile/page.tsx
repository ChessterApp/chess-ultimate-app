'use client'

import { useUser, useClerk } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useTranslations, useLocale } from 'next-intl'
import { useEffect, useState } from 'react'
import { Avatar } from '@/components/gamification/Avatar'
import { CelebrationController } from '@/components/gamification/CelebrationController'
import { StreakBanner } from '@/components/gamification/StreakBanner'
import { XPDisplay } from '@/components/gamification/XPDisplay'
import LoadingScreen from '@/components/LoadingScreen'
import FamilySection from './FamilySection'
import type { CEAchievement } from '@/lib/chess-empire-client'
import type { GamificationProfile } from '@/lib/gamification/profile'
import type { ItemRow } from '@/lib/gamification/items'

/** Pick the rank name for the active locale (kz → Kazakh column). */
function rankName(
  rank: NonNullable<GamificationProfile['rank']>,
  locale: string,
): string {
  if (locale === 'ru') return rank.name_ru
  if (locale === 'kz') return rank.name_kk
  return rank.name_en
}

export default function ProfilePage() {
  const { user, isLoaded } = useUser()
  const { signOut } = useClerk()
  const router = useRouter()
  const t = useTranslations()
  const locale = useLocale()

  const [profile, setProfile] = useState<GamificationProfile | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(true)
  const [equipped, setEquipped] = useState<Partial<Record<string, ItemRow>>>({})
  const [achievements, setAchievements] = useState<CEAchievement[]>([])

  useEffect(() => {
    if (!isLoaded || !user) return
    let cancelled = false
    fetch('/api/gamification/profile')
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!cancelled) setProfile(data)
      })
      .catch(() => {
        if (!cancelled) setProfile(null)
      })
      .finally(() => {
        if (!cancelled) setLoadingProfile(false)
      })

    // Composited avatar loadout (§9.1) — resolve the equipped item per slot.
    fetch('/api/gamification/inventory')
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { items: ItemRow[]; loadout: Record<string, string> } | null) => {
        if (cancelled || !data) return
        const byId = new Map(data.items.map((it) => [it.id, it]))
        const eq: Partial<Record<string, ItemRow>> = {}
        for (const [slot, itemId] of Object.entries(data.loadout ?? {})) {
          const it = byId.get(itemId)
          if (it) eq[slot] = it
        }
        setEquipped(eq)
      })
      .catch(() => {})

    // Achievements strip (§9.1, repaired §3).
    fetch('/api/gamification/achievements')
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { achievements: CEAchievement[] } | null) => {
        if (!cancelled && data) setAchievements(data.achievements ?? [])
      })
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [isLoaded, user])

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

  const linked = profile?.linked === true

  return (
    <div className="min-h-screen bg-gray-50 animate-page-enter">
      {/* Rank-up / streak-milestone celebrations (§3, §5.5) */}
      <CelebrationController profile={profile} />

      {/* Profile Header */}
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center gap-4">
            {linked ? (
              <Avatar equipped={equipped} photoUrl={user.imageUrl} size={80} className="shrink-0" />
            ) : (
              <div className="w-20 h-20 rounded-full bg-white/20 flex items-center justify-center overflow-hidden">
                {user.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.imageUrl} alt={user.firstName || 'Profile'} className="w-full h-full object-cover" />
                ) : (
                  <span className="text-4xl">👤</span>
                )}
              </div>
            )}
            <div className="flex-1">
              <h1 className="text-2xl font-bold">{user.firstName || 'Chess Player'}</h1>
              <p className="text-purple-200">{user.emailAddresses[0]?.emailAddress}</p>
              {linked && profile && (
                <div className="flex items-center gap-3 mt-2 flex-wrap">
                  <XPDisplay xp={profile.xp} size="sm" />
                  {profile.rank && (
                    <>
                      <span className="text-purple-200">•</span>
                      <span className="text-sm text-purple-100">
                        {t('gamification.rankLabel')}: {rankName(profile.rank, locale)}
                      </span>
                    </>
                  )}
                  <span className="text-purple-200">•</span>
                  <span className="flex items-center gap-1 text-sm">
                    <span className="text-yellow-300">🪙</span>
                    <span>{profile.coins}</span>
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6 space-y-6">
        {loadingProfile ? (
          <div className="bg-white rounded-2xl shadow-md p-6 text-center text-gray-500">…</div>
        ) : linked && profile ? (
          <>
            {/* Rank + progress */}
            {profile.rank && (
              <div className="bg-white rounded-2xl shadow-md p-6">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-3">
                    {profile.rank.icon_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={profile.rank.icon_url} alt="" className="w-9 h-9 object-contain" />
                    ) : (
                      <span className="text-3xl">♟️</span>
                    )}
                    <div>
                      <div className="text-xs uppercase tracking-wide text-gray-400">
                        {t('gamification.rankLabel')}
                      </div>
                      <div className="text-xl font-bold text-gray-900">
                        {rankName(profile.rank, locale)}
                      </div>
                    </div>
                  </div>
                  <XPDisplay xp={profile.xp} size="lg" />
                </div>
                <div className="h-3 w-full rounded-full bg-gray-100 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-purple-500 to-amber-400 transition-all"
                    style={{ width: `${profile.rank_progress.pct}%` }}
                  />
                </div>
                <div className="mt-2 text-sm text-gray-500">
                  {profile.rank_progress.next_code
                    ? t('gamification.toNextRank', {
                        xp: Math.max(
                          0,
                          profile.rank_progress.xp_for_next - profile.rank_progress.xp_into_rank,
                        ),
                      })
                    : t('gamification.maxRank')}
                </div>
              </div>
            )}

            {/* Tournament-week streak */}
            <StreakBanner
              streakDays={profile.streak.current_weeks}
              unit="weeks"
              nextMilestone={profile.streak.next_milestone}
            />

            {/* Stats since launch */}
            <div className="bg-white rounded-2xl shadow-md p-6">
              <h2 className="text-lg font-bold text-gray-900 mb-1">{t('profile.yourStats')}</h2>
              <p className="text-xs text-gray-400 mb-4">{t('gamification.sinceLaunch')}</p>
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-purple-50 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-purple-600">{profile.stats.tournaments_played}</div>
                  <div className="text-sm text-gray-600">{t('gamification.tournaments')}</div>
                </div>
                <div className="bg-green-50 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-green-600">{profile.stats.wins_total}</div>
                  <div className="text-sm text-gray-600">{t('gamification.wins')}</div>
                </div>
                <div className="bg-yellow-50 rounded-xl p-4 text-center">
                  <div className="text-3xl font-bold text-yellow-600">{profile.coins}</div>
                  <div className="text-sm text-gray-600">{t('gamification.coins')}</div>
                </div>
              </div>
            </div>

            {/* Cosmetics: customize avatar + shop */}
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => router.push('/avatar')}
                className="bg-white rounded-2xl shadow-md p-6 text-center hover:bg-gray-50 transition-colors"
              >
                <div className="text-3xl mb-1">🎨</div>
                <div className="font-semibold text-gray-900">{t('gamification.shop.customize')}</div>
              </button>
              <button
                onClick={() => router.push('/shop')}
                className="bg-white rounded-2xl shadow-md p-6 text-center hover:bg-gray-50 transition-colors"
              >
                <div className="text-3xl mb-1">🛍️</div>
                <div className="font-semibold text-gray-900">{t('gamification.shop.title')}</div>
              </button>
            </div>

            {/* Legion & Cup */}
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => router.push('/legion')}
                className="bg-white rounded-2xl shadow-md p-6 text-center hover:bg-gray-50 transition-colors"
              >
                <div className="text-3xl mb-1">
                  {profile.legion?.crest_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={profile.legion.crest_url} alt="" className="w-10 h-10 mx-auto" />
                  ) : (
                    '🛡️'
                  )}
                </div>
                <div className="font-semibold text-gray-900">
                  {profile.legion?.name || t('gamification.legion.title')}
                </div>
              </button>
              <button
                onClick={() => router.push('/cup')}
                className="bg-white rounded-2xl shadow-md p-6 text-center hover:bg-gray-50 transition-colors"
              >
                <div className="text-3xl mb-1">🏆</div>
                <div className="font-semibold text-gray-900">{t('gamification.cup.title')}</div>
              </button>
            </div>

            {/* Trophy case — «Зал славы» (§7.4) */}
            <div className="bg-white rounded-2xl shadow-md p-6">
              <h2 className="text-lg font-bold text-gray-900 mb-4">
                🏆 {t('gamification.trophies.title')}
              </h2>
              {profile.trophies.length === 0 ? (
                <p className="text-sm text-gray-400">{t('gamification.trophies.empty')}</p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  {profile.trophies.map((tr) => (
                    <div
                      key={tr.item_id}
                      className="rounded-xl border border-amber-200 bg-amber-50 p-3 flex flex-col items-center text-center"
                    >
                      {tr.art_url && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={tr.art_url} alt="" className="w-16 h-16 mb-2" />
                      )}
                      <div className="text-sm font-semibold text-gray-900">
                        {locale === 'ru' ? tr.name_ru : locale === 'kz' ? tr.name_kk : tr.name_en}
                      </div>
                      {tr.acquisition_note && (
                        <div className="text-xs text-amber-700 mt-1">{tr.acquisition_note}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Achievements strip (§9.1) */}
            <div className="bg-white rounded-2xl shadow-md p-6">
              <h2 className="text-lg font-bold text-gray-900 mb-4">
                🏅 {t('empire.achievementsTitle')}
              </h2>
              {achievements.length === 0 ? (
                <p className="text-sm text-gray-400">{t('empire.achievementsEmpty')}</p>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
                  {achievements.slice(0, 9).map((a) => (
                    <div
                      key={a.id}
                      className="rounded-xl border border-gray-100 bg-gray-50 p-3 flex flex-col items-center text-center"
                    >
                      {a.icon_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={a.icon_url} alt="" className="w-12 h-12 mb-2" />
                      ) : (
                        <div className="text-3xl mb-2">🏅</div>
                      )}
                      <div className="text-sm font-semibold text-gray-900">{a.name}</div>
                      {a.description && (
                        <div className="text-xs text-gray-500 mt-0.5">{a.description}</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          /* Unlinked (D-8): gamification hidden until the account is linked. */
          <div className="bg-white rounded-2xl shadow-md p-6 text-center">
            <div className="text-4xl mb-2">🔗</div>
            <h2 className="text-lg font-bold text-gray-900 mb-1">{t('gamification.notLinkedTitle')}</h2>
            <p className="text-sm text-gray-500">{t('gamification.notLinkedBody')}</p>
          </div>
        )}

        {/* Family — verified Chess Empire members on this account (self-hides
            when there are none). */}
        <FamilySection />

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
