import React, { useState } from 'react'
import {
  Box,
  Typography,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions,
} from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { gameTheme } from '@/data/bots'
import { playText } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'

interface GameDockProps {
  bot: Bot
  /** Resolved player color for this game. */
  playerColor: 'w' | 'b'
  /** Result text once the game has ended (null while in progress). */
  gameResult: string | null
  onNewGame: () => void
  /** End the game as a loss for the player. */
  onResign: () => void
}

const INK = '#28324E'
const INK_SOFT = '#5C6784'
const RESIGN_TEXT = '#E5484D'
const RESIGN_BORDER = '#FFD3D5'

/**
 * V3 "Immersive World" bottom dock: a white rounded card with the player line
 * (color disc + status) and two pill actions — Resign (with a kid-friendly
 * confirm dialog) and New game. There is intentionally no Hint button.
 */
export default function GameDock({
  bot,
  playerColor,
  gameResult,
  onNewGame,
  onResign,
}: GameDockProps) {
  const t = useTranslations('bots')
  const { main, deep, tint, screenGradient } = gameTheme(bot)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const colorLabel =
    playerColor === 'w'
      ? playText(t, 'white', 'White')
      : playText(t, 'black', 'Black')

  const subtitle = gameResult ?? playText(t, 'gameInProgress', 'game in progress')

  const handleConfirmResign = () => {
    setConfirmOpen(false)
    onResign()
  }

  return (
    <Box
      data-testid="game-dock"
      data-tier={bot.tier}
      sx={{
        bgcolor: 'rgba(255,255,255,.95)',
        borderRadius: '18px',
        p: 1.5,
        boxShadow: `0 10px 26px ${deep}40`,
      }}
    >
      {/* Player line */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25 }}>
        <Box
          aria-hidden="true"
          sx={{
            width: 38,
            height: 38,
            borderRadius: '50%',
            bgcolor: tint,
            border: `2px solid ${main}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '20px',
            color: INK,
            flexShrink: 0,
          }}
        >
          {playerColor === 'w' ? '♔' : '♚'}
        </Box>
        <Box sx={{ minWidth: 0, fontFamily: nunito.style.fontFamily }}>
          <Typography
            component="div"
            sx={{ fontWeight: 900, fontSize: '14px', color: INK, lineHeight: 1.2 }}
          >
            {playText(t, 'youAreColor', `You — ${colorLabel}`, { color: colorLabel })}
          </Typography>
          <Typography
            component="div"
            sx={{ fontWeight: 800, fontSize: '12px', color: INK_SOFT, lineHeight: 1.2 }}
          >
            {subtitle}
          </Typography>
        </Box>
      </Box>

      {/* Actions */}
      <Box sx={{ display: 'flex', gap: 1.25, mt: 1.5 }}>
        {!gameResult && (
          <Box
            component="button"
            type="button"
            data-testid="resign-button"
            onClick={() => setConfirmOpen(true)}
            sx={{
              flex: 1,
              bgcolor: '#fff',
              color: RESIGN_TEXT,
              border: `2px solid ${RESIGN_BORDER}`,
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '14.5px',
              borderRadius: '999px',
              py: '11px',
              px: '16px',
              cursor: 'pointer',
              boxShadow: `0 4px 10px ${RESIGN_TEXT}1F`,
              transition: 'background-color 120ms ease',
              '&:hover': { bgcolor: '#FFF5F5' },
            }}
          >
            🏳️ {playText(t, 'resign', 'Resign')}
          </Box>
        )}
        <Box
          component="button"
          type="button"
          data-testid="new-game-button"
          onClick={onNewGame}
          sx={{
            flex: 1,
            background: screenGradient,
            color: '#fff',
            border: 'none',
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            fontSize: '14.5px',
            borderRadius: '999px',
            py: '11px',
            px: '16px',
            cursor: 'pointer',
            boxShadow: `0 6px 14px ${deep}4D`,
          }}
        >
          🔁 {playText(t, 'newGame', 'New game')}
        </Box>
      </Box>

      {/* Resign confirm dialog */}
      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        data-testid="resign-dialog"
        PaperProps={{ sx: { borderRadius: '20px', p: 1 } }}
      >
        <DialogTitle
          sx={{ fontFamily: fredoka.style.fontFamily, fontWeight: 700, color: INK }}
        >
          {playText(t, 'resignConfirmTitle', 'Give up this game?')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText
            sx={{ fontFamily: nunito.style.fontFamily, fontWeight: 700, color: INK_SOFT }}
          >
            {playText(
              t,
              'resignConfirmBody',
              `If you give up, ${bot.name} wins. You can start a new game any time!`,
              { name: bot.name },
            )}
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <Box
            component="button"
            type="button"
            data-testid="resign-cancel"
            onClick={() => setConfirmOpen(false)}
            sx={{
              bgcolor: tint,
              color: deep,
              border: `2px solid ${main}`,
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '14px',
              borderRadius: '999px',
              py: '9px',
              px: '18px',
              cursor: 'pointer',
            }}
          >
            {playText(t, 'resignConfirmCancel', 'Keep playing')}
          </Box>
          <Box
            component="button"
            type="button"
            data-testid="resign-confirm"
            onClick={handleConfirmResign}
            sx={{
              bgcolor: RESIGN_TEXT,
              color: '#fff',
              border: 'none',
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '14px',
              borderRadius: '999px',
              py: '9px',
              px: '18px',
              cursor: 'pointer',
            }}
          >
            {playText(t, 'resignConfirmYes', 'Yes, I give up')}
          </Box>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
