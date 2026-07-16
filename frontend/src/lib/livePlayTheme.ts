import type { EndModalTheme } from '@/components/play/GameEndModalBase'

/**
 * Fixed online-play palette — a calm blue→teal consistent with the play
 * section's "Play a friend" card (`#2E6BFF`). Online games are not per-opponent
 * themed, so this is hardcoded the same way `gameTheme` bakes bot colors.
 */
export const LIVE_PLAY_THEME: EndModalTheme = {
  main: '#2E6BFF',
  deep: '#1B49B8',
  tint: '#E5EEFF',
  screenGradient: 'linear-gradient(160deg, #2E6BFF 0%, #22D3EE 55%, #7DD3FC 100%)',
}

/** Neutral ink shared across the online-play chrome. */
export const LIVE_INK = '#1E2A44'
export const LIVE_INK_SOFT = '#5C6B85'
