'use client'

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
import { fredoka, nunito } from '@/lib/fonts'
import { LIVE_PLAY_THEME, LIVE_INK, LIVE_INK_SOFT } from '@/lib/livePlayTheme'

interface LiveGameDockProps {
  /** The viewer's color this game. */
  playerColor: 'white' | 'black'
  /** Preformatted viewer clock (e.g. "5:00" / "∞"). */
  clock: string
  /** Highlight the clock while it's the viewer's move. */
  clockActive: boolean
  /** The viewer already sent a standing draw offer. */
  drawOfferedByMe: boolean
  /** The opponent offered a draw and the viewer must accept/decline. */
  drawOfferedByOpponent: boolean
  /** An abort is still legal (game active, <2 plies). */
  canAbort: boolean
  onAbort: () => void
  onOfferDraw: () => void
  onAcceptDraw: () => void
  onDeclineDraw: () => void
  onResign: () => void
}

const RESIGN_TEXT = '#E5484D'
const RESIGN_BORDER = '#FFD3D5'

/** A rounded pill action button in the online-play card language. */
function PillButton({
  children,
  onClick,
  disabled,
  testId,
  variant,
}: {
  children: React.ReactNode
  onClick: () => void
  disabled?: boolean
  testId: string
  variant: 'primary' | 'ghost' | 'danger'
}) {
  const { main, tint, deep } = LIVE_PLAY_THEME
  const styles =
    variant === 'danger'
      ? { bgcolor: '#fff', color: RESIGN_TEXT, border: `2px solid ${RESIGN_BORDER}` }
      : variant === 'primary'
        ? { bgcolor: main, color: '#fff', border: 'none', boxShadow: `0 6px 14px ${deep}4D` }
        : { bgcolor: tint, color: deep, border: `2px solid ${main}` }
  return (
    <Box
      component="button"
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      sx={{
        fontFamily: nunito.style.fontFamily,
        fontWeight: 800,
        fontSize: '14px',
        borderRadius: '999px',
        py: '10px',
        px: '16px',
        cursor: disabled ? 'default' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        ...styles,
      }}
    >
      {children}
    </Box>
  )
}

/**
 * Online-play bottom dock — a white rounded card in the bot game's `GameDock`
 * language. Hosts the viewer's player line + clock, the draw-offer accept /
 * decline banner, and the in-game actions (Abort when legal, Offer draw,
 * Resign behind a kid-friendly confirm dialog).
 */
export default function LiveGameDock({
  playerColor,
  clock,
  clockActive,
  drawOfferedByMe,
  drawOfferedByOpponent,
  canAbort,
  onAbort,
  onOfferDraw,
  onAcceptDraw,
  onDeclineDraw,
  onResign,
}: LiveGameDockProps) {
  const { main, tint, deep } = LIVE_PLAY_THEME
  const [confirmOpen, setConfirmOpen] = useState(false)

  const handleConfirmResign = () => {
    setConfirmOpen(false)
    onResign()
  }

  return (
    <Box
      data-testid="live-game-dock"
      sx={{
        bgcolor: 'rgba(255,255,255,.95)',
        borderRadius: '18px',
        p: 1.5,
        boxShadow: `0 10px 26px ${deep}33`,
      }}
    >
      {/* Player line + clock */}
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
            color: LIVE_INK,
            flexShrink: 0,
          }}
        >
          {playerColor === 'white' ? '♔' : '♚'}
        </Box>
        <Box sx={{ minWidth: 0, flex: 1, fontFamily: nunito.style.fontFamily }}>
          <Typography
            component="div"
            sx={{ fontWeight: 900, fontSize: '14px', color: LIVE_INK, lineHeight: 1.2 }}
          >
            You — {playerColor === 'white' ? 'White' : 'Black'}
          </Typography>
          <Typography
            component="div"
            sx={{ fontWeight: 800, fontSize: '12px', color: LIVE_INK_SOFT, lineHeight: 1.2 }}
          >
            {clockActive ? 'Your move' : 'Their move'}
          </Typography>
        </Box>
        <Box
          data-testid="player-clock"
          sx={{
            px: 1.75,
            py: 0.75,
            borderRadius: '12px',
            bgcolor: clockActive ? LIVE_INK : '#EEF2FA',
            color: clockActive ? '#fff' : LIVE_INK,
            fontVariantNumeric: 'tabular-nums',
            fontWeight: 900,
            fontSize: 20,
            minWidth: 72,
            textAlign: 'center',
            flexShrink: 0,
          }}
        >
          {clock}
        </Box>
      </Box>

      {/* Draw-offer banner */}
      {drawOfferedByOpponent && (
        <Box
          data-testid="draw-offer-banner"
          sx={{
            mt: 1.5,
            p: 1.5,
            borderRadius: '14px',
            bgcolor: tint,
            border: `1px solid ${main}`,
          }}
        >
          <Typography
            sx={{
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '13.5px',
              mb: 1,
              color: LIVE_INK,
            }}
          >
            Opponent offers a draw
          </Typography>
          <Box sx={{ display: 'flex', gap: 1 }}>
            <PillButton testId="accept-draw" variant="primary" onClick={onAcceptDraw}>
              Accept
            </PillButton>
            <PillButton testId="decline-draw" variant="ghost" onClick={onDeclineDraw}>
              Decline
            </PillButton>
          </Box>
        </Box>
      )}

      {/* Actions */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1.5 }}>
        {canAbort && (
          <PillButton testId="abort" variant="ghost" onClick={onAbort}>
            Abort
          </PillButton>
        )}
        <PillButton
          testId="offer-draw"
          variant="ghost"
          onClick={onOfferDraw}
          disabled={drawOfferedByMe}
        >
          {drawOfferedByMe ? 'Draw offered' : 'Offer draw'}
        </PillButton>
        <PillButton testId="resign" variant="danger" onClick={() => setConfirmOpen(true)}>
          🏳️ Resign
        </PillButton>
      </Box>

      {/* Resign confirm dialog — kid-friendly, mirrors the bot GameDock. */}
      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        data-testid="resign-dialog"
        PaperProps={{ sx: { borderRadius: '20px', p: 1 } }}
      >
        <DialogTitle
          sx={{ fontFamily: fredoka.style.fontFamily, fontWeight: 700, color: LIVE_INK }}
        >
          Give up this game?
        </DialogTitle>
        <DialogContent>
          <DialogContentText
            sx={{ fontFamily: nunito.style.fontFamily, fontWeight: 700, color: LIVE_INK_SOFT }}
          >
            If you give up, your opponent wins. You can start a new game any time!
          </DialogContentText>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2, gap: 1 }}>
          <PillButton
            testId="resign-cancel"
            variant="ghost"
            onClick={() => setConfirmOpen(false)}
          >
            Keep playing
          </PillButton>
          <Box
            component="button"
            type="button"
            data-testid="confirm-resign"
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
            Yes, I give up
          </Box>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
