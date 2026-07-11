'use client'

import { useCallback, useEffect, useRef } from 'react'

/**
 * Syncs a component's in-route "phase" state to the URL query string via the
 * browser History API, so the Back button steps through the flow's screens
 * instead of leaving the page.
 *
 * Design notes (see .ralphy/back-nav-fix-brief.md):
 * - Forward transitions use `pushState` (NOT `router.push`, which refetches;
 *   NOT `replaceState`, which wouldn't create Back entries). App Router
 *   tolerates native `pushState`/`replaceState` without a navigation.
 * - `replace()` corrects the current entry's URL without adding history.
 * - `back()` pops one entry, which fires `popstate` → `onRestore`.
 * - `onRestore` runs both on mount (deep-link / refresh restore, `initial:
 *   true`) and on every `popstate` (`initial: false`), so the component can
 *   rebuild the screen from the URL.
 * - SSR-safe: every `window` access is guarded or lives inside an effect.
 */
export type PhaseParams = Record<string, string | number | null | undefined>

export interface RestoreMeta<T> {
  /** True on the mount restore (deep-link / refresh), false on popstate. */
  initial: boolean
  /** Correct the current entry's URL without adding history. */
  replace: (phase: T) => void
  /** Add a new history entry. */
  push: (phase: T) => void
}

export interface PhaseHistoryConfig<T> {
  /** Parse the phase value from the current URL query params. */
  parse: (params: URLSearchParams) => T
  /** Serialize a phase value to query params; `undefined`/`null`/'' are removed. */
  serialize: (phase: T) => PhaseParams
  /** Restore the screen from a parsed phase (mount + popstate). */
  onRestore: (phase: T, meta: RestoreMeta<T>) => void
}

function currentSearch(): URLSearchParams {
  if (typeof window === 'undefined') return new URLSearchParams()
  return new URLSearchParams(window.location.search)
}

export function usePhaseHistory<T>(config: PhaseHistoryConfig<T>) {
  // Keep the latest callbacks in refs so the popstate listener stays stable
  // (registered once) while always seeing fresh component state. The refs are
  // seeded with the first render's callbacks and refreshed after each render.
  const parseRef = useRef(config.parse)
  const serializeRef = useRef(config.serialize)
  const onRestoreRef = useRef(config.onRestore)
  useEffect(() => {
    parseRef.current = config.parse
    serializeRef.current = config.serialize
    onRestoreRef.current = config.onRestore
  })

  const buildUrl = useCallback((phase: T) => {
    const params = new URLSearchParams(window.location.search)
    const next = serializeRef.current(phase)
    for (const [key, value] of Object.entries(next)) {
      if (value === undefined || value === null || value === '') params.delete(key)
      else params.set(key, String(value))
    }
    const qs = params.toString()
    return `${window.location.pathname}${qs ? `?${qs}` : ''}`
  }, [])

  const push = useCallback((phase: T) => {
    if (typeof window === 'undefined') return
    window.history.pushState(null, '', buildUrl(phase))
  }, [buildUrl])

  const replace = useCallback((phase: T) => {
    if (typeof window === 'undefined') return
    window.history.replaceState(null, '', buildUrl(phase))
  }, [buildUrl])

  const back = useCallback(() => {
    if (typeof window === 'undefined') return
    window.history.back()
  }, [])

  useEffect(() => {
    const meta = { replace, push }
    // Restore from the URL on mount (deep-link + refresh).
    onRestoreRef.current(parseRef.current(currentSearch()), { ...meta, initial: true })

    const handler = () => {
      onRestoreRef.current(parseRef.current(currentSearch()), { ...meta, initial: false })
    }
    window.addEventListener('popstate', handler)
    return () => window.removeEventListener('popstate', handler)
    // Intentionally run once; callbacks are read through refs.
  }, [push, replace])

  return { push, replace, back }
}
