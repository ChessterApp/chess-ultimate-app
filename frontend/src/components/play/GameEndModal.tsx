'use client'

import React, { useEffect } from 'react'
import { Box, Typography } from '@mui/material'
import { motion, useReducedMotion } from 'framer-motion'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { BOTS, gameTheme } from '@/data/bots'
import { fredoka, nunito } from '@/lib/fonts'
import { useSoundEffects } from '@/hooks/useSoundEffects'
import LottieCelebration from '@/components/chess/LottieCelebration'
import BotAvatar from './BotAvatar'
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
const INK_SOFT = '#5C6784'

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
 * no hardcoded palette. Win pops confetti + trophy + stars; loss bounces the
 * bot with an encouraging nudge; draw is a neutral handshake card.
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
  const reduce = useReducedMotion()
  const { play } = useSoundEffects()
  const { main, deep, tint, screenGradient } = gameTheme(bot)

  // Next bot in the ladder (for "Try a stronger bot"); null on the last bot.
  const idx = BOTS.findIndex((b) => b.id === bot.id)
  const nextBot = idx >= 0 && idx < BOTS.length - 1 ? BOTS[idx + 1] : null

  // Win chime only — no sound on loss/draw.
  useEffect(() => {
    if (open && outcome === 'playerWin') play('success')
  }, [open, outcome, play])

  if (!open) return null

  const title =
    outcome === 'playerWin'
      ? t('winTitle')
      : outcome === 'draw'
        ? t('drawTitle')
        : t(resigned ? 'resignTitle' : 'lossTitle', { botName: bot.name })

  const announcement =
    outcome === 'playerWin'
      ? t('ariaResult', { botName: bot.name })
      : outcome === 'draw'
        ? `${t('drawTitle')} ${t('drawSubtitle')}`
        : title

  const bubbleText = outcome === 'playerWin' ? t('winBubble') : t('lossBubble')
  const showConfetti = outcome === 'playerWin' && !reduce

  // Entrance choreography is skipped entirely under prefers-reduced-motion.
  const cardMotion = reduce
    ? {}
    : {
        initial: { opacity: 0, scale: 0.85, y: 20 },
        animate: { opacity: 1, scale: 1, y: 0 },
        transition: { type: 'spring' as const, stiffness: 320, damping: 24 },
      }

  const emblemMotion = reduce
    ? {}
    : {
        initial: { scale: 0, rotate: -30 },
        animate: { scale: 1, rotate: 0 },
        transition: { type: 'spring' as const, stiffness: 500, damping: 14, delay: 0.1 },
      }

  const avatarMotion =
    reduce || outcome !== 'botWin'
      ? {}
      : {
          animate: { y: [0, -8, 0] },
          transition: { duration: 0.6, repeat: 2, ease: 'easeInOut' as const },
        }

  return (
    <Box
      data-testid="game-end-modal"
      data-outcome={outcome}
      role="dialog"
      aria-modal="true"
      aria-labelledby="game-end-title"
      sx={{
        position: 'fixed',
        inset: 0,
        zIndex: 1320,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        p: 2,
        fontFamily: nunito.style.fontFamily,
      }}
    >
      {/* aria-live region — announces the localized result when the modal opens. */}
      <Box
        aria-live="assertive"
        sx={{
          position: 'absolute',
          width: 1,
          height: 1,
          overflow: 'hidden',
          clip: 'rect(0 0 0 0)',
          whiteSpace: 'nowrap',
        }}
      >
        {announcement}
      </Box>

      {/* Dimmed backdrop — click dismisses. */}
      <Box
        data-testid="game-end-backdrop"
        onClick={onClose}
        sx={{ position: 'absolute', inset: 0, bgcolor: 'rgba(15,23,42,.55)' }}
      />

      {showConfetti && (
        <Box data-testid="game-end-confetti">
          <LottieCelebration visible fullScreen duration={2600} />
        </Box>
      )}

      <motion.div
        {...cardMotion}
        style={{
          position: 'relative',
          zIndex: 1,
          width: '100%',
          maxWidth: 380,
          borderRadius: 24,
          overflow: 'hidden',
          background: '#fff',
          boxShadow: '0 24px 60px rgba(15,23,42,.35)',
        }}
      >
        {/* Close button */}
        <Box
          component="button"
          type="button"
          data-testid="game-end-close"
          aria-label="Close"
          onClick={onClose}
          sx={{
            position: 'absolute',
            top: 12,
            right: 12,
            zIndex: 2,
            width: 34,
            height: 34,
            borderRadius: '50%',
            border: 'none',
            bgcolor: 'rgba(255,255,255,.85)',
            color: INK,
            fontSize: 18,
            fontWeight: 800,
            lineHeight: 1,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          ✕
        </Box>

        {/* Themed header band */}
        <Box
          sx={{
            background: screenGradient,
            height: 96,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {outcome === 'playerWin' && (
            <motion.div {...emblemMotion} style={{ fontSize: 56, lineHeight: 1 }}>
              🏆
            </motion.div>
          )}
          {outcome === 'draw' && (
            <motion.div {...emblemMotion} style={{ fontSize: 56, lineHeight: 1 }}>
              🤝
            </motion.div>
          )}
        </Box>

        <Box sx={{ px: 3, pt: 2.5, pb: 3, textAlign: 'center' }}>
          {/* Avatar + speech bubble (win & loss only) */}
          {outcome !== 'draw' && (
            <Box
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                mt: -8,
                mb: 1.5,
              }}
            >
              <motion.div {...avatarMotion}>
                <BotAvatar
                  bot={bot}
                  size={84}
                  ringColor="#fff"
                  ringWidth={4}
                  tint={tint}
                  deep={deep}
                  sx={{ boxShadow: `0 10px 24px ${deep}59` }}
                />
              </motion.div>
              <Box
                data-testid="game-end-bubble"
                sx={{
                  mt: 1.25,
                  bgcolor: tint,
                  color: deep,
                  borderRadius: '16px 16px 16px 4px',
                  px: '14px',
                  py: '8px',
                  fontWeight: 800,
                  fontSize: '14px',
                  maxWidth: 260,
                }}
              >
                {bubbleText}
              </Box>
            </Box>
          )}

          <Typography
            id="game-end-title"
            data-testid="game-end-title"
            component="h2"
            sx={{
              fontFamily: fredoka.style.fontFamily,
              fontWeight: 700,
              fontSize: outcome === 'draw' ? '24px' : '22px',
              color: INK,
              lineHeight: 1.15,
              mt: outcome === 'draw' ? 1 : 0,
            }}
          >
            {title}
          </Typography>

          {/* Stars (win only) */}
          {outcome === 'playerWin' && (
            <Box sx={{ display: 'flex', justifyContent: 'center', gap: 0.75, mt: 1.25 }}>
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  data-testid="game-end-star"
                  initial={reduce ? undefined : { scale: 0 }}
                  animate={reduce ? undefined : { scale: 1 }}
                  transition={
                    reduce
                      ? undefined
                      : { type: 'spring', stiffness: 500, damping: 12, delay: 0.35 + i * 0.15 }
                  }
                  style={{ fontSize: 30, lineHeight: 1, color: main }}
                >
                  ⭐
                </motion.span>
              ))}
            </Box>
          )}

          {/* Subtitle (loss encourage / draw) */}
          {outcome === 'botWin' && (
            <Typography
              sx={{ mt: 1.25, fontWeight: 700, fontSize: '14px', color: INK_SOFT }}
            >
              {t('lossEncourage')}
            </Typography>
          )}
          {outcome === 'draw' && (
            <Typography
              sx={{ mt: 1, fontWeight: 700, fontSize: '14px', color: INK_SOFT }}
            >
              {t('drawSubtitle')}
            </Typography>
          )}

          {/* Actions */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.25, mt: 2.5 }}>
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
          </Box>
        </Box>
      </motion.div>
    </Box>
  )
}
