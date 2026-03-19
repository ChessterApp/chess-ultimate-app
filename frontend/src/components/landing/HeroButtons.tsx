'use client'

import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'

export function HeroButtons() {
  const router = useRouter()
  const t = useTranslations()

  return (
    <div className="flex flex-col gap-3 w-full max-w-md pb-8 lg:pb-0">
      <button
        onClick={() => router.push('/sign-up')}
        className="w-full bg-white hover:bg-purple-50 text-purple-700 px-8 py-4 rounded-2xl font-bold text-base lg:text-lg uppercase tracking-wider transition-all duration-200 transform hover:scale-105 shadow-lg hover:shadow-xl active:scale-95 border-b-4 border-purple-200 active:border-b-2 active:translate-y-0.5"
      >
        {t('common.getStarted')}
      </button>

      <button
        onClick={() => router.push('/sign-in')}
        className="w-full bg-transparent border-2 border-white/40 hover:bg-white/10 text-white px-8 py-4 rounded-2xl font-bold text-base lg:text-lg uppercase tracking-wider transition-all duration-200 active:translate-y-0.5"
      >
        {t('landing.alreadyHaveAccount')}
      </button>
    </div>
  )
}
