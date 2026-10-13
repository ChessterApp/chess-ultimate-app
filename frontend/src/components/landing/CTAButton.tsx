'use client'

import { useRouter } from 'next/navigation'
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events'

export function CTAButton({ href, children, className, location }: {
  href: string,
  children: React.ReactNode,
  className?: string,
  /** Landing section, for `landing_cta_clicked` (hero / pricing / footer). */
  location: 'hero' | 'pricing' | 'footer',
}) {
  const router = useRouter()

  return (
    <button
      onClick={() => {
        track(ANALYTICS_EVENTS.LANDING_CTA_CLICKED, { location, target: href })
        router.push(href)
      }}
      className={className}
    >
      {children}
    </button>
  )
}
