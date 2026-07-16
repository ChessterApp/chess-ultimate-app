'use client';

/**
 * Live game page (phase 3) — one route, driven entirely by `useLiveGame`.
 *
 * States: lobby (creator waiting on a challenge), joining (recipient accepting),
 * playing (active board), and a terminal result banner. Resign/draw/flag
 * controls are phase 4; this page only renders an already-terminal game cleanly.
 *
 * Gated behind ONLINE_PLAY_ENABLED — the whole route 404s when the flag is off.
 */

import React, { useState } from 'react';
import { useParams, notFound } from 'next/navigation';
import { Box, Button, Typography, CircularProgress, Chip } from '@mui/material';
import { Chess } from 'chess.js';
import type { Key } from 'chessground/types';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import { useLiveGame } from '@/hooks/useLiveGame';
import { ONLINE_PLAY_ENABLED } from '@/lib/feature-flags';

const INVITE_BASE = 'https://chesster.io';

/** ms → m:ss (or ∞ for an untimed bank). */
function fmtClock(ms: number | null): string {
  if (ms === null) return '∞';
  const total = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/** Time-control label from initial/increment seconds. */
function tcLabel(initialSec: number | null, incrementSec: number | null): string {
  if (initialSec === null) return 'Untimed';
  return `${Math.floor(initialSec / 60)} + ${incrementSec ?? 0}`;
}

/** Build the UCI for a board drag, auto-queening a promotion. */
function moveToUci(fen: string, from: Key, to: Key): string | null {
  try {
    const chess = new Chess(fen);
    const legal = chess.moves({ verbose: true });
    const m = legal.find((mv) => mv.from === from && mv.to === to);
    if (!m) return null;
    const promo = m.promotion ? 'q' : '';
    return `${from}${to}${promo}`;
  } catch {
    return null;
  }
}

function CenterCard({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ maxWidth: 560, mx: 'auto', p: { xs: 2, sm: 4 } }}>
      <Box
        sx={{
          p: { xs: 3, sm: 4 },
          borderRadius: '24px',
          bgcolor: '#FFFFFF',
          border: '1px solid #E3EAF6',
          boxShadow: '0 12px 32px rgba(30,60,120,0.10)',
          textAlign: 'center',
        }}
      >
        {children}
      </Box>
    </Box>
  );
}

export default function LiveGamePage() {
  const params = useParams<{ gameId: string }>();
  const gameId = params?.gameId ?? '';
  const game = useLiveGame(gameId);
  const [copied, setCopied] = useState(false);
  const [accepting, setAccepting] = useState(false);

  if (!ONLINE_PLAY_ENABLED) notFound();

  const inviteUrl = `${INVITE_BASE}/play/live/${gameId}`;

  const copyLink = async () => {
    try {
      await navigator.clipboard?.writeText(inviteUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard unavailable */
    }
  };

  const accept = async () => {
    setAccepting(true);
    const ok = await game.join();
    if (!ok) setAccepting(false);
  };

  const handleMove = (from: Key, to: Key) => {
    const uci = moveToUci(game.fen, from, to);
    if (uci) void game.makeMove(uci);
  };

  // ── Loading ─────────────────────────────────────────────────────────────────
  if (game.loading) {
    return (
      <CenterCard>
        <CircularProgress />
        <Typography sx={{ mt: 2, color: '#5C6B85' }}>Loading game…</Typography>
      </CenterCard>
    );
  }

  // ── Hard errors (not found / expired / unauthorized) ────────────────────────
  if (game.error === 'not_found') {
    return (
      <CenterCard>
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>
          Game not found
        </Typography>
        <Typography sx={{ color: '#5C6B85' }}>
          This challenge link is invalid or has been removed.
        </Typography>
      </CenterCard>
    );
  }
  if (game.status === 'expired' || game.error === 'expired') {
    return (
      <CenterCard>
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>
          Challenge expired
        </Typography>
        <Typography sx={{ color: '#5C6B85' }}>
          This challenge is no longer available. Ask your friend for a new link.
        </Typography>
      </CenterCard>
    );
  }

  // ── Terminal result banner ──────────────────────────────────────────────────
  if (game.terminal.isOver) {
    const { outcome, reason } = game.terminal;
    const heading =
      outcome === 'win' ? 'You won!' : outcome === 'loss' ? 'You lost' : 'Game drawn';
    return (
      <Box sx={{ maxWidth: 720, mx: 'auto', p: { xs: 2, sm: 3 } }}>
        <CenterCard>
          <Typography variant="h4" sx={{ fontWeight: 900, mb: 1 }}>
            {heading}
          </Typography>
          <Typography sx={{ color: '#5C6B85', mb: 2 }}>
            {game.terminal.result}
            {reason ? ` · ${reason.replace(/_/g, ' ')}` : ''}
          </Typography>
        </CenterCard>
        <Box
          sx={{
            maxWidth: 520,
            mx: 'auto',
            borderRadius: '16px',
            overflow: 'hidden',
            lineHeight: 0,
          }}
        >
          <ChessgroundBoard
            fen={game.fen}
            orientation={game.orientation}
            movable={false}
            viewOnly
          />
        </Box>
      </Box>
    );
  }

  // ── Lobby (creator waiting on a challenge) ──────────────────────────────────
  if (game.status === 'challenge' && game.isCreator) {
    return (
      <CenterCard>
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>
          Waiting for your opponent…
        </Typography>
        <Typography sx={{ color: '#5C6B85', mb: 3 }}>
          Share this link. The game starts automatically when they join.
        </Typography>
        <Box
          sx={{
            display: 'flex',
            gap: 1,
            alignItems: 'center',
            justifyContent: 'center',
            flexWrap: 'wrap',
          }}
        >
          <Box
            sx={{
              px: 2,
              py: 1,
              borderRadius: '10px',
              bgcolor: '#F3F7FF',
              border: '1px solid #E3EAF6',
              fontFamily: 'monospace',
              fontSize: 13,
              color: '#1E2A44',
              maxWidth: '100%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {inviteUrl}
          </Box>
          <Button
            variant="contained"
            onClick={copyLink}
            data-testid="copy-link"
            sx={{ borderRadius: '999px', textTransform: 'none', fontWeight: 700 }}
          >
            {copied ? 'Copied!' : 'Copy link'}
          </Button>
        </Box>
        <Typography variant="caption" sx={{ display: 'block', mt: 3, color: '#8A97AD' }}>
          {tcLabel(game.initialSec, game.incrementSec)} ·{' '}
          {game.colorChoice === 'random' ? 'random colors' : `you play ${game.colorChoice}`}
        </Typography>
      </CenterCard>
    );
  }

  // ── Joining (recipient accepting a challenge) ───────────────────────────────
  if (game.status === 'challenge' && !game.isCreator) {
    const creatorColor =
      game.colorChoice === 'random' ? 'a random color' : game.colorChoice;
    return (
      <CenterCard>
        <Typography variant="h5" sx={{ fontWeight: 800, mb: 1 }}>
          You&apos;ve been challenged!
        </Typography>
        <Typography sx={{ color: '#5C6B85', mb: 3 }}>
          {tcLabel(game.initialSec, game.incrementSec)} · the creator plays {creatorColor}.
        </Typography>
        {game.error && game.error !== 'not_found' && (
          <Typography variant="body2" sx={{ color: '#C62828', mb: 2 }}>
            Could not join: {game.error.replace(/_/g, ' ')}
          </Typography>
        )}
        <Button
          variant="contained"
          onClick={accept}
          disabled={accepting}
          data-testid="accept-challenge"
          sx={{
            borderRadius: '999px',
            textTransform: 'none',
            fontWeight: 800,
            px: 4,
            py: 1.25,
          }}
        >
          {accepting ? 'Joining…' : 'Accept & play'}
        </Button>
      </CenterCard>
    );
  }

  // ── Playing (active board) ──────────────────────────────────────────────────
  const topClock = game.orientation === 'white' ? game.clocks.blackMs : game.clocks.whiteMs;
  const bottomClock = game.orientation === 'white' ? game.clocks.whiteMs : game.clocks.blackMs;

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', p: { xs: 1, sm: 3 } }}>
      <Box
        sx={{
          display: 'grid',
          gap: 2,
          alignItems: 'start',
          justifyContent: { md: 'center' },
          gridTemplateColumns: { xs: '1fr', md: 'auto 300px' },
        }}
      >
        <Box>
          <ClockRow ms={topClock} active={!game.isMyTurn} />
          <Box
            sx={{
              borderRadius: '16px',
              overflow: 'hidden',
              border: '4px solid #FFFFFF',
              boxShadow: '0 12px 32px rgba(30,60,120,0.14)',
              lineHeight: 0,
              my: 1,
            }}
          >
            <ChessgroundBoard
              fen={game.fen}
              orientation={game.orientation}
              onMove={handleMove}
              movable={game.isMyTurn}
            />
          </Box>
          <ClockRow ms={bottomClock} active={game.isMyTurn} />
        </Box>

        <Box>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
            <Chip
              size="small"
              label={game.opponentConnected ? 'Opponent online' : 'Opponent offline'}
              color={game.opponentConnected ? 'success' : 'default'}
              variant={game.opponentConnected ? 'filled' : 'outlined'}
            />
            <Chip
              size="small"
              label={game.isMyTurn ? 'Your turn' : 'Their turn'}
              variant="outlined"
            />
          </Box>
          <Typography variant="caption" sx={{ fontWeight: 700, color: '#5C6B85' }}>
            MOVES
          </Typography>
          <MoveList moves={game.moves} />
        </Box>
      </Box>
    </Box>
  );
}

function ClockRow({ ms, active }: { ms: number | null; active: boolean }) {
  return (
    <Box
      sx={{
        display: 'inline-flex',
        px: 2,
        py: 0.75,
        borderRadius: '10px',
        bgcolor: active ? '#1E2A44' : '#EEF2FA',
        color: active ? '#FFFFFF' : '#1E2A44',
        fontVariantNumeric: 'tabular-nums',
        fontWeight: 800,
        fontSize: 22,
        minWidth: 84,
        justifyContent: 'center',
      }}
    >
      {fmtClock(ms)}
    </Box>
  );
}

function MoveList({
  moves,
}: {
  moves: Array<{ ply: number; san: string | null; uci: string }>;
}) {
  return (
    <Box
      sx={{
        mt: 0.5,
        maxHeight: 360,
        overflowY: 'auto',
        display: 'grid',
        gridTemplateColumns: 'auto 1fr 1fr',
        rowGap: 0.25,
        columnGap: 1,
        fontSize: 14,
      }}
    >
      {Array.from({ length: Math.ceil(moves.length / 2) }).map((_, i) => {
        const white = moves[i * 2];
        const black = moves[i * 2 + 1];
        return (
          <React.Fragment key={i}>
            <Box sx={{ color: '#8A97AD' }}>{i + 1}.</Box>
            <Box sx={{ fontWeight: 600 }}>{white?.san ?? white?.uci ?? ''}</Box>
            <Box sx={{ fontWeight: 600 }}>{black?.san ?? black?.uci ?? ''}</Box>
          </React.Fragment>
        );
      })}
    </Box>
  );
}
