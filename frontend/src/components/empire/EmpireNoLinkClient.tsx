'use client'

/**
 * Client wrapper for the Chess Empire `no_link` dashboard state.
 *
 * The member row is written asynchronously — by the Clerk `user.created`
 * webhook, by the server-side pending-cookie auto-claim, and (for OAuth signups
 * that dropped `unsafeMetadata`) by the client-side claim. Any of these can
 * land after the dashboard first renders, which would otherwise strand the user
 * on the static "no link" screen.
 *
 * On every mount (initial load, `router.refresh`, or the manual Refresh button)
 * this:
 *   1. Replays any stashed invite JWT to `/api/chess-empire/link/claim`. The
 *      server accepts an expired-but-signed JWT within a 24h grace window, and
 *      falls back to the `ce_pending_jti` cookie → pending row. The stashed JWT
 *      is cleared ONLY on success or a signature-class (`invalid`) terminal —
 *      an expiry never wipes it, since the server may still accept it.
 *   2. Polls `/api/chess-empire/link/status` with capped exponential backoff
 *      (up to ~10 min) and `router.refresh()`es the moment the state leaves
 *      `no_link`. After the cap it shows the static screen plus a Refresh
 *      action that restarts polling; any fresh page load restarts it too.
 */
import { useCallback, useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import {
  CE_INVITE_JWT_STORAGE_KEY,
  readBranchWelcomeUrl,
} from '@/lib/invite-storage'

// Keep polling slowly for ~10 min before falling back to the manual Refresh.
const POLL_MAX_MS = 10 * 60_000
const POLL_BASE_MS = 2_000
const POLL_MAX_INTERVAL_MS = 30_000

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
  // Bumping this re-runs the claim + poll cycle (Refresh button / restart).
  const [runId, setRunId] = useState(0)
  const [startOverUrl, setStartOverUrl] = useState<string | null>(null)

  useEffect(() => {
    // localStorage isn't available during SSR, so this must read in an effect.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setStartOverUrl(readBranchWelcomeUrl())
  }, [])

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
        // Only a signature-class terminal is truly hopeless. An expired JWT may
        // still be claimable later via the server-side pending row, so keep it.
        if (data?.error === 'invalid') clearStoredJwt()
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
  }, [router, runId])

  const restart = useCallback(() => {
    setPolling(true)
    setRunId((n) => n + 1)
  }, [])

  if (polling) {
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
          {startOverUrl && (
            <a
              data-testid="empire-nolink-startover"
              href={startOverUrl}
              className="text-sm font-semibold text-slate-500 underline underline-offset-4 hover:text-slate-700"
            >
              {t('noLinkStartOver')}
            </a>
          )}
        </div>
      </main>
    )
  }

  // Polling gave up (cap reached) — show the static screen, but keep an
  // escape hatch: Refresh restarts polling, Start over re-runs onboarding.
  return (
    <>
      {children}
      <div
        data-testid="empire-nolink-stalled"
        className="fixed inset-x-0 bottom-0 z-40 flex flex-wrap items-center justify-center gap-3 border-t border-slate-200 bg-white/95 px-4 py-3 text-sm shadow-[0_-1px_8px_rgba(0,0,0,0.06)] backdrop-blur"
      >
        <button
          type="button"
          data-testid="empire-nolink-refresh"
          onClick={restart}
          className="rounded-full bg-slate-900 px-4 py-2 font-semibold text-white hover:bg-slate-700"
        >
          {t('noLinkRefresh')}
        </button>
        {startOverUrl && (
          <a
            data-testid="empire-nolink-startover"
            href={startOverUrl}
            className="font-semibold text-slate-500 underline underline-offset-4 hover:text-slate-700"
          >
            {t('noLinkStartOver')}
          </a>
        )}
      </div>
    </>
  )
}
