'use client'

import React from 'react'
import { Box } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { BOTS, gameTheme } from '@/data/bots'
import { nunito } from '@/lib/fonts'
import BotAvatar from './BotAvatar'
import GameEndModalBase from './GameEndModalBase'
import type { GameOutcome } from '@/lib/gameOutcome'

interface GameEndModalProps {
  bot: Bot
  /** Result from the player's point of view. */
  outcome: GameOutcome
  /** botWin that came from the player resigning (uses resignTitle). */
  resigned?: boolean
  open: boolean
  /** Dismiss (X / backdrop) — leaves the board reviewable underneath. */
  onClose: () => void
  /** Play again / Rematch: fresh game vs the same bot. */
  onPlayAgain: () => void
  /** Start a fresh game vs the next (stronger) bot in BOTS order. */
  onTryStronger: (nextBot: Bot) => void
  /** Back to bot selection. */
  onChooseAnother: () => void
}

const INK = '#28324E'

/** Pick readable text (dark ink / white) for a solid accent background. */
function readableText(hex: string): string {
  const h = hex.replace('#', '')
  if (h.length < 6) return '#fff'
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.62 ? INK : '#fff'
}

/**
 * "Variation B" celebratory result modal shown ~0.8s after a bot game ends.
 * Themed entirely from {@link gameTheme} so every bot gets its own colors with
 * no hardcoded palette. The layout/celebration/sound live in
 * {@link GameEndModalBase}; this wrapper supplies the bot avatar and the
 * bot-specific actions (Play again / Try a stronger bot / Choose another bot).
 */
export default function GameEndModal({
  bot,
  outcome,
  resigned = false,
  open,
  onClose,
  onPlayAgain,
  onTryStronger,
  onChooseAnother,
}: GameEndModalProps) {
  const t = useTranslations('gameEnd')
  const theme = gameTheme(bot)
  const { main, deep, tint } = theme

  // Next bot in the ladder (for "Try a stronger bot"); null on the last bot.
  const idx = BOTS.findIndex((b) => b.id === bot.id)
  const nextBot = idx >= 0 && idx < BOTS.length - 1 ? BOTS[idx + 1] : null

  const avatar = (
    <BotAvatar
      bot={bot}
      size={84}
      ringColor="#fff"
      ringWidth={4}
      tint={tint}
      deep={deep}
      sx={{ boxShadow: `0 10px 24px ${deep}59` }}
    />
  )

  const actions = (
    <>
      <Box
        component="button"
        type="button"
        data-testid="game-end-primary"
        onClick={onPlayAgain}
        sx={{
          bgcolor: main,
          color: readableText(main),
          border: 'none',
          fontFamily: nunito.style.fontFamily,
          fontWeight: 800,
          fontSize: '15px',
          borderRadius: '999px',
          py: '12px',
          cursor: 'pointer',
          boxShadow: `0 8px 18px ${deep}4D`,
        }}
      >
        {outcome === 'botWin' ? t('rematch') : t('playAgain')}
      </Box>

      {outcome === 'playerWin' && nextBot && (
        <Box
          component="button"
          type="button"
          data-testid="game-end-secondary"
          onClick={() => onTryStronger(nextBot)}
          sx={{
            bgcolor: tint,
            color: deep,
            border: `2px solid ${main}`,
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            fontSize: '15px',
            borderRadius: '999px',
            py: '10px',
            cursor: 'pointer',
          }}
        >
          {t('tryStronger')}
        </Box>
      )}

      {outcome === 'botWin' && (
        <Box
          component="button"
          type="button"
          data-testid="game-end-secondary"
          onClick={onChooseAnother}
          sx={{
            bgcolor: tint,
            color: deep,
            border: `2px solid ${main}`,
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            fontSize: '15px',
            borderRadius: '999px',
            py: '10px',
            cursor: 'pointer',
          }}
        >
          {t('chooseAnother')}
        </Box>
      )}
    </>
  )

  return (
    <GameEndModalBase
      theme={theme}
      outcome={outcome}
      resigned={resigned}
      opponentName={bot.name}
      avatar={avatar}
      actions={actions}
      open={open}
      onClose={onClose}
    />
  )
}
