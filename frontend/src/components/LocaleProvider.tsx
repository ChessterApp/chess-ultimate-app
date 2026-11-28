'use client'

import { createContext, startTransition, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'
import { useRouter } from 'next/navigation'
import { NextIntlClientProvider, type AbstractIntlMessages } from 'next-intl'
import type { Locale } from '@/i18n/config'
import { substituteAppName } from '@/lib/i18n-substitute'
import { useOrganization } from '@/contexts/OrganizationContext'
import { persistPreferredLocale } from '@/lib/preferred-locale'

const messageCache = new Map<string, Promise<AbstractIntlMessages>>()

/** Raw (unsubstituted) messages for `locale`, imported once per page life. */
function loadMessages(locale: string): Promise<AbstractIntlMessages> {
  let loading = messageCache.get(locale)
  if (!loading) {
    loading = import(`../../messages/${locale}.json`).then((m) => m.default as AbstractIntlMessages)
    // Don't cache a failure (offline): the next attempt retries the import.
    loading.catch(() => messageCache.delete(locale))
    messageCache.set(locale, loading)
  }
  return loading
}

function writeLocaleCookie(locale: string) {
  document.cookie = `NEXT_LOCALE=${locale}; path=/; max-age=31536000; SameSite=Lax`
}

interface LocaleSwitch {
  switchLocale: (locale: Locale) => Promise<void>
  prefetchLocale: (locale: Locale) => void
  /** True only while the picked locale's messages are loading. */
  isSwitching: boolean
}

const LocaleSwitchContext = createContext<LocaleSwitch | null>(null)

export function useLocaleSwitch(): LocaleSwitch {
  const value = useContext(LocaleSwitchContext)
  if (!value) throw new Error('useLocaleSwitch must be used inside <LocaleProvider>')
  return value
}

interface LocaleProviderProps {
  serverLocale: string
  serverMessages: AbstractIntlMessages
  timeZone?: string
  children: ReactNode
}

interface LocaleState {
  locale: string
  messages: AbstractIntlMessages
  /** Locale of a client switch the server hasn't rendered yet. */
  pending: string | null
}

/**
 * Client-side owner of the active locale. A switch swaps the messages in
 * place as soon as they're imported (no server round-trip), then refreshes
 * the server tree in the background; server payloads that predate the switch
 * are ignored so they can't flip the screen back.
 */
export default function LocaleProvider({ serverLocale, serverMessages, timeZone, children }: LocaleProviderProps) {
  const router = useRouter()
  const { org } = useOrganization()
  const appName = org?.name || 'Chesster'
  const [state, setState] = useState<LocaleState>({ locale: serverLocale, messages: serverMessages, pending: null })
  // Latest requested locale, so a superseded switch drops its result.
  const targetRef = useRef<string | null>(null)

  // Reconcile with a new server payload (router.refresh / navigation landed).
  const [server, setServer] = useState({ locale: serverLocale, messages: serverMessages })
  if (server.locale !== serverLocale || server.messages !== serverMessages) {
    setServer({ locale: serverLocale, messages: serverMessages })
    if (state.pending === null || state.pending === serverLocale) {
      // Our switch confirmed, or a server-driven change (e.g. the saved preference after login).
      setState({ locale: serverLocale, messages: serverMessages, pending: null })
    } else if (serverLocale === state.locale) {
      // Same locale, switch still loading: server messages are authoritative.
      setState({ ...state, messages: serverMessages })
    }
    // Otherwise a stale payload from before the switch: ignore it.
  }

  const switchLocale = useCallback(async (locale: Locale) => {
    targetRef.current = locale
    setState((s) => ({ ...s, pending: locale }))
    let messages: AbstractIntlMessages | null = null
    try {
      messages = substituteAppName(await loadMessages(locale), appName)
    } catch {
      // Offline: fall back to the cookie + server render below.
    }
    if (targetRef.current !== locale) return
    // Before the swap: effects keyed on useLocale() fire server requests that read it.
    writeLocaleCookie(locale)
    if (messages) {
      setState({ locale, messages, pending: locale })
      document.documentElement.lang = locale
    } else {
      setState((s) => ({ ...s, pending: null }))
    }
    startTransition(() => router.refresh())
    void persistPreferredLocale(locale)
  }, [appName, router])

  const prefetchLocale = useCallback((locale: Locale) => {
    loadMessages(locale).catch(() => {})
  }, [])

  const isSwitching = state.pending !== null && state.pending !== state.locale
  const value = useMemo(
    () => ({ switchLocale, prefetchLocale, isSwitching }),
    [switchLocale, prefetchLocale, isSwitching],
  )

  return (
    <LocaleSwitchContext.Provider value={value}>
      <NextIntlClientProvider locale={state.locale} messages={state.messages} timeZone={timeZone}>
        {children}
      </NextIntlClientProvider>
    </LocaleSwitchContext.Provider>
  )
}
