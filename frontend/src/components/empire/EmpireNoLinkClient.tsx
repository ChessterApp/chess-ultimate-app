'use client'

/**
 * Client wrapper for the Chess Empire `no_link` dashboard state.
 *
 * The member row is written asynchronously — by the Clerk `user.created`
 * webhook, and (for OAuth signups that dropped `unsafeMetadata`) by the
 * client-side claim. Either can land after the dashboard first renders, which
 * would otherwise strand the user on the static "no link" screen.
 *
 * On mount this:
 *   1. Replays any stashed invite JWT to `/api/chess-empire/link/claim`
 *      (the OAuth-metadata-loss fallback), clearing storage on success or a
 *      terminal error.
 *   2. Polls `/api/chess-empire/link/status` (~2s, backing off, ~60s cap) and
 *      `router.refresh()`es as soon as the state leaves `no_link`.
 *
 * While polling it shows a subtle spinner; after the cap it renders `children`
 * — the server-rendered static `no_link` message.
 */
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { CE_INVITE_JWT_STORAGE_KEY } from '@/lib/invite-storage'

const POLL_MAX_MS = 60_000
const POLL_BASE_MS = 2_000
const POLL_MAX_INTERVAL_MS = 8_000

function readStoredJwt(): string | null {
  try {
    return (
      sessionStorage.getItem(CE_INVITE_JWT_STORAGE_KEY) ||
      localStorage.getItem(CE_INVITE_JWT_STORAGE_KEY)
    )
  } catch {
    return null
  }
}

function clearStoredJwt(): void {
  try {
    sessionStorage.removeItem(CE_INVITE_JWT_STORAGE_KEY)
    localStorage.removeItem(CE_INVITE_JWT_STORAGE_KEY)
  } catch {
    // ignore — storage unavailable
  }
}

export default function EmpireNoLinkClient({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const t = useTranslations('empire')
  const [polling, setPolling] = useState(true)

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const start = Date.now()
    let attempt = 0

    const linked = () => {
      if (cancelled) return
      setPolling(false)
      router.refresh()
    }

    async function claimIfPresent(): Promise<void> {
      const jwt = readStoredJwt()
      if (!jwt) return
      try {
        const res = await fetch('/api/chess-empire/link/claim', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ inviteJwt: jwt }),
        })
        if (res.ok) {
          clearStoredJwt()
          linked()
          return
        }
        const data = await res.json().catch(() => ({}))
        if (data?.terminal) clearStoredJwt()
      } catch {
        // Network hiccup — polling still runs and the webhook is the backstop.
      }
    }

    async function pollStatus(): Promise<void> {
      if (cancelled) return
      if (Date.now() - start >= POLL_MAX_MS) {
        setPolling(false)
        return
      }
      try {
        const res = await fetch('/api/chess-empire/link/status')
        if (res.ok) {
          const data = await res.json()
          if (data?.state && data.state !== 'no_link') {
            linked()
            return
          }
        }
      } catch {
        // ignore — retry on the next tick
      }
      attempt += 1
      const delay = Math.min(
        POLL_MAX_INTERVAL_MS,
        Math.round(POLL_BASE_MS * Math.pow(1.4, attempt - 1)),
      )
      timer = setTimeout(pollStatus, delay)
    }

    void (async () => {
      await claimIfPresent()
      if (!cancelled) void pollStatus()
    })()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [router])

  if (!polling) return <>{children}</>

  return (
    <main
      data-testid="empire-home-nolink-polling"
      className="min-h-screen px-4 sm:px-6 lg:px-10 py-12 lg:py-20"
      style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
    >
      <div className="max-w-2xl mx-auto text-center flex flex-col items-center gap-4">
        <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 text-white p-8 sm:p-10 shadow-sm w-full">
          <div className="flex items-center justify-center gap-3">
            <span
              aria-hidden
              className="inline-block h-5 w-5 animate-spin rounded-full border-2 border-slate-500 border-t-white"
            />
            <h1 className="text-xl md:text-2xl font-semibold tracking-tight">
              {t('settingUpProfile')}
            </h1>
          </div>
          <p className="mt-3 text-slate-300 text-sm">{t('noLinkSubtitle')}</p>
        </div>
      </div>
    </main>
  )
}
