import { useEffect, useRef } from 'react'

/**
 * Re-fetches locale-dependent data in place after a soft language switch.
 *
 * `loadedLocale` is the locale the data on screen was fetched in (null until
 * the first load). Whenever it differs from the live `locale`, `refetch` runs
 * and `apply` receives the result — so nothing happens on first mount, and a
 * switch made while the first load was in flight is caught up once it lands.
 * A response is dropped if the locale moves on before it arrives; a failed
 * refetch leaves the old text on screen.
 */
export function useLocaleRefresh<T>(
  locale: string,
  loadedLocale: string | null,
  refetch: (locale: string) => Promise<T>,
  apply: (data: T, locale: string) => void,
) {
  const refetchRef = useRef(refetch)
  const applyRef = useRef(apply)
  useEffect(() => {
    refetchRef.current = refetch
    applyRef.current = apply
  })

  useEffect(() => {
    if (loadedLocale === null || loadedLocale === locale) return
    let stale = false
    refetchRef.current(locale).then(
      (data) => { if (!stale) applyRef.current(data, locale) },
      (err) => console.warn('Locale refresh failed:', err),
    )
    return () => { stale = true }
  }, [locale, loadedLocale])
}
