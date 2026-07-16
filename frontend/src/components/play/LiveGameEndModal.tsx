'use client'

import React, { useState } from 'react'
import { Box } from '@mui/material'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { fredoka, nunito } from '@/lib/fonts'
import { LIVE_PLAY_THEME } from '@/lib/livePlayTheme'
import GameEndModalBase from './GameEndModalBase'
import type { GameOutcome } from '@/lib/gameOutcome'

interface LiveGameEndModalProps {
  /** Result from the player's point of view. */
  outcome: GameOutcome
  /** A loss that came from the player resigning. */
  resigned?: boolean
  /** Opponent display name (initial-letter avatar is derived from it). */
  opponentName: string
  /** Player's color this game — the rematch swaps it. */
  myColor: 'white' | 'black' | null
  /** Time control to reuse for the rematch challenge. */
  initialSec: number | null
  incrementSec: number | null
  open: boolean
  onClose: () => void
}

const LIVE_THEME = LIVE_PLAY_THEME

/** Initial-letter avatar for an opponent with no portrait. */
function InitialAvatar({ name }: { name: string }) {
  const letter = (name.trim()[0] ?? '?').toUpperCase()
  return (
    <Box
      aria-hidden="true"
      sx={{
        width: 84,
        height: 84,
        borderRadius: '50%',
        bgcolor: LIVE_THEME.tint,
        color: LIVE_THEME.deep,
        border: '4px solid #fff',
        boxShadow: `0 10px 24px ${LIVE_THEME.deep}59`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: fredoka.style.fontFamily,
        fontWeight: 700,
        fontSize: 38,
        lineHeight: 1,
      }}
    >
      {letter}
    </Box>
  )
}

/**
 * The online-play result modal — the bot game's celebratory core
 * ({@link GameEndModalBase}) with an opponent avatar and online actions:
 * **Rematch** (creates a fresh challenge with the same time control and colors
 * swapped, copies the invite link, and opens the new lobby) and **Back to
 * Play**. No "try a stronger bot" equivalent.
 */
export default function LiveGameEndModal({
  outcome,
  resigned = false,
  opponentName,
  myColor,
  initialSec,
  incrementSec,
  open,
  onClose,
}: LiveGameEndModalProps) {
  const t = useTranslations('gameEnd')
  const router = useRouter()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(false)

  const rematch = async () => {
    if (busy) return
    setBusy(true)
    setError(false)
    // Colors swapped: whoever plays the rematch creator role takes the other
    // side. 'random' if we somehow never resolved a color.
    const colorChoice =
      myColor === 'white' ? 'black' : myColor === 'black' ? 'white' : 'random'
    try {
      const res = await fetch('/api/games/challenge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ colorChoice, initialSec, incrementSec }),
      })
      if (!res.ok) {
        setError(true)
        setBusy(false)
        return
      }
      const { gameId, url } = (await res.json()) as { gameId: string; url: string }
      // Best-effort copy the invite link; navigation is what matters.
      try {
        await navigator.clipboard?.writeText(url)
      } catch {
        /* clipboard may be unavailable (permissions / non-secure ctx) */
      }
      router.push(`/play/live/${gameId}`)
    } catch {
      setError(true)
      setBusy(false)
    }
  }

  const backToPlay = () => router.push('/play')

  const actions = (
    <>
      {error && (
        <Box
          data-testid="live-end-error"
          sx={{
            fontFamily: nunito.style.fontFamily,
            fontWeight: 700,
            fontSize: '13px',
            color: '#C62828',
          }}
        >
          {t('rematchFailed')}
        </Box>
      )}
      <Box
        component="button"
        type="button"
        data-testid="live-end-rematch"
        onClick={rematch}
        disabled={busy}
        sx={{
          bgcolor: LIVE_THEME.main,
          color: '#fff',
          border: 'none',
          fontFamily: nunito.style.fontFamily,
          fontWeight: 800,
          fontSize: '15px',
          borderRadius: '999px',
          py: '12px',
          cursor: busy ? 'default' : 'pointer',
          opacity: busy ? 0.7 : 1,
          boxShadow: `0 8px 18px ${LIVE_THEME.deep}4D`,
        }}
      >
        {busy ? t('rematchCreating') : t('rematch')}
      </Box>
      <Box
        component="button"
        type="button"
        data-testid="live-end-back"
        onClick={backToPlay}
        sx={{
          bgcolor: LIVE_THEME.tint,
          color: LIVE_THEME.deep,
          border: `2px solid ${LIVE_THEME.main}`,
          fontFamily: nunito.style.fontFamily,
          fontWeight: 800,
          fontSize: '15px',
          borderRadius: '999px',
          py: '10px',
          cursor: 'pointer',
        }}
      >
        {t('backToPlay')}
      </Box>
    </>
  )

  return (
    <GameEndModalBase
      theme={LIVE_THEME}
      outcome={outcome}
      resigned={resigned}
      opponentName={opponentName}
      avatar={<InitialAvatar name={opponentName} />}
      actions={actions}
      open={open}
      onClose={onClose}
    />
  )
}
