'use client'

import { useEffect, useState, type RefObject } from 'react'

// The player never became ready (blocked script, offline) → unlock after this.
const NOT_READY_FALLBACK_MS = 15000
// The player reported an error → unlock after this.
const ERROR_FALLBACK_MS = 3000
const YT_ENDED = 0

interface YTPlayerEvent {
  data: number
}

interface YTApi {
  Player: new (
    el: HTMLIFrameElement,
    opts: { events: { onReady: () => void; onStateChange: (e: YTPlayerEvent) => void; onError: () => void } },
  ) => unknown
}

declare global {
  interface Window {
    YT?: YTApi
    onYouTubeIframeAPIReady?: () => void
  }
}

let apiPromise: Promise<YTApi> | null = null

function loadYouTubeApi(): Promise<YTApi> {
  if (window.YT?.Player) return Promise.resolve(window.YT)
  if (!apiPromise) {
    apiPromise = new Promise((resolve, reject) => {
      const prev = window.onYouTubeIframeAPIReady
      window.onYouTubeIframeAPIReady = () => {
        prev?.()
        resolve(window.YT as YTApi)
      }
      const script = document.createElement('script')
      script.src = 'https://www.youtube.com/iframe_api'
      script.onerror = () => {
        apiPromise = null
        reject(new Error('YouTube IFrame API failed to load'))
      }
      document.head.appendChild(script)
    })
  }
  return apiPromise
}

/**
 * True once every YouTube video embedded in `containerRef` has played to the
 * end (IFrame Player API `onStateChange` ENDED). If the API or a player fails,
 * turns true after a short delay so the user is never stuck.
 */
export function useYouTubeEnded(containerRef: RefObject<HTMLElement | null>, enabled: boolean): boolean {
  const [done, setDone] = useState(false)

  useEffect(() => {
    if (!enabled) return
    let cancelled = false
    const timers: number[] = []
    const unlockAfter = (ms: number) => {
      timers.push(window.setTimeout(() => { if (!cancelled) setDone(true) }, ms))
    }

    const iframes = Array.from(
      containerRef.current?.querySelectorAll<HTMLIFrameElement>('iframe[src*="youtube.com/embed/"]') ?? [],
    )
    if (iframes.length === 0) {
      unlockAfter(ERROR_FALLBACK_MS)
      return () => { cancelled = true; timers.forEach(clearTimeout) }
    }

    const notReadyTimer = window.setTimeout(() => { if (!cancelled) setDone(true) }, NOT_READY_FALLBACK_MS)
    timers.push(notReadyTimer)
    const ready = new Set<number>()
    const ended = new Set<number>()

    loadYouTubeApi()
      .then((YT) => {
        if (cancelled) return
        iframes.forEach((iframe, i) => {
          new YT.Player(iframe, {
            events: {
              onReady: () => {
                ready.add(i)
                if (ready.size === iframes.length) clearTimeout(notReadyTimer)
              },
              onStateChange: (e) => {
                if (e.data !== YT_ENDED || cancelled) return
                ended.add(i)
                if (ended.size === iframes.length) setDone(true)
              },
              onError: () => unlockAfter(ERROR_FALLBACK_MS),
            },
          })
        })
      })
      .catch(() => unlockAfter(ERROR_FALLBACK_MS))

    return () => {
      cancelled = true
      timers.forEach(clearTimeout)
    }
  }, [containerRef, enabled])

  return done
}
