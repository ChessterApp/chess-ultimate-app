'use client';

/**
 * Live game page (phase 3–5) — one route, driven entirely by `useLiveGame`.
 *
 * States: lobby (creator waiting on a challenge), joining (recipient accepting),
 * playing (active board with header/dock chrome), and a terminal result. Phase 5
 * reskins the UI to the bot-game design language: rounded white cards, world
 * scenery behind the board, and the celebratory `LiveGameEndModal` on a real
 * result (aborted/expired games keep their quiet banner — an abandoned game is
 * not a result).
 *
 * Gated behind ONLINE_PLAY_ENABLED — the whole route 404s when the flag is off.
 */

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, notFound } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';
import { Box, Typography } from '@mui/material';
import { useReducedMotion } from 'framer-motion';
import { Chess } from 'chess.js';
import type { Key } from 'chessground/types';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import WorldScenery from '@/components/play/WorldScenery';
import LiveGameHeader from '@/components/play/LiveGameHeader';
import LiveGameDock from '@/components/play/LiveGameDock';
import LiveGameEndModal from '@/components/play/LiveGameEndModal';
import { useLiveGame } from '@/hooks/useLiveGame';
import { liveOutcome } from '@/lib/liveOutcome';
import { fredoka, nunito } from '@/lib/fonts';
import { LIVE_PLAY_THEME, LIVE_INK, LIVE_INK_SOFT } from '@/lib/livePlayTheme';
import { ONLINE_PLAY_ENABLED } from '@/lib/feature-flags';
import LiveGameGuard from './LiveGameGuard';

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

/** Rounded white card in the play-section language, centered on the page. */
function CenterCard({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ maxWidth: 520, mx: 'auto', p: { xs: 2, sm: 4 } }}>
      <Box
        sx={{
          p: { xs: 3, sm: 4 },
          borderRadius: '24px',
          bgcolor: '#FFFFFF',
          border: '1px solid #E3EAF6',
          boxShadow: '0 12px 32px rgba(30,60,120,0.10)',
          textAlign: 'center',
          fontFamily: nunito.style.fontFamily,
        }}
      >
        {children}
      </Box>
    </Box>
  );
}

/** Fredoka heading used across the lobby / accept / status cards. */
function CardTitle({ children }: { children: React.ReactNode }) {
  return (
    <Typography
      component="h1"
      sx={{
        fontFamily: fredoka.style.fontFamily,
        fontWeight: 700,
        fontSize: { xs: 22, sm: 26 },
        color: LIVE_INK,
        mb: 1,
      }}
    >
      {children}
    </Typography>
  );
}

/** Primary pill button in the online-play language. */
function PrimaryPill({
  children,
  onClick,
  href,
  disabled,
  testId,
}: {
  children: React.ReactNode;
  onClick?: () => void;
  href?: string;
  disabled?: boolean;
  testId?: string;
}) {
  const sx = {
    display: 'inline-block',
    bgcolor: LIVE_PLAY_THEME.main,
    color: '#fff',
    border: 'none',
    fontFamily: nunito.style.fontFamily,
    fontWeight: 800,
    fontSize: '15px',
    borderRadius: '999px',
    py: '12px',
    px: 4,
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.65 : 1,
    textDecoration: 'none',
    boxShadow: `0 8px 18px ${LIVE_PLAY_THEME.deep}33`,
  } as const;
  if (href) {
    return (
      <Box component={Link} href={href} data-testid={testId} sx={sx}>
        {children}
      </Box>
    );
  }
  return (
    <Box component="button" type="button" onClick={onClick} disabled={disabled} data-testid={testId} sx={sx}>
      {children}
    </Box>
  );
}

export default function LiveGamePage() {
  if (!ONLINE_PLAY_ENABLED) notFound();
  // Tenant hosts skip Clerk edge auth (middleware pass-through); guard signed-out
  // visitors here before the game view fires any authed API calls.
  return (
    <LiveGameGuard>
      <LiveGameView />
    </LiveGameGuard>
  );
}

function LiveGameView() {
  const params = useParams<{ gameId: string }>();
  const gameId = params?.gameId ?? '';
  const { userId } = useAuth();
  const game = useLiveGame(gameId);
  const reduce = useReducedMotion();
  const [copied, setCopied] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const inviteUrl = `${INVITE_BASE}/play/live/${gameId}`;

  // Reveal the result modal ~0.8s after a game ends so the final position is
  // visible first. Reduced-motion users skip the deliberate delay. Only a real
  // result (not an abort/expiry) shows the modal.
  const outcome = game.terminal.isOver
    ? liveOutcome(
        {
          winnerId: game.terminal.winnerId,
          result: game.terminal.result,
          reason: game.terminal.reason,
        },
        userId ?? null,
      )
    : null;

  const hasResult = outcome !== null;
  useEffect(() => {
    if (!hasResult) return;
    const delay = reduce ? 0 : 800;
    const timer = setTimeout(() => setModalOpen(true), delay);
    return () => clearTimeout(timer);
  }, [hasResult, reduce]);

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
        <CardTitle>Loading game…</CardTitle>
        <Typography sx={{ color: LIVE_INK_SOFT }}>Setting up the board.</Typography>
      </CenterCard>
    );
  }

  // ── Hard errors (not found / expired) ───────────────────────────────────────
  if (game.error === 'not_found') {
    return (
      <CenterCard>
        <CardTitle>Game not found</CardTitle>
        <Typography sx={{ color: LIVE_INK_SOFT }}>
          This challenge link is invalid or has been removed.
        </Typography>
      </CenterCard>
    );
  }
  if (game.status === 'expired' || game.error === 'expired') {
    return (
      <CenterCard>
        <CardTitle>Challenge expired</CardTitle>
        <Typography sx={{ color: LIVE_INK_SOFT, mb: 3 }}>
          This challenge is no longer available. Ask your friend for a new link.
        </Typography>
        <PrimaryPill href="/play" testId="new-challenge">
          Create a new challenge
        </PrimaryPill>
      </CenterCard>
    );
  }

  // ── Terminal result ─────────────────────────────────────────────────────────
  if (game.terminal.isOver) {
    // Aborted / expired: no result, keep a quiet banner (an abandoned game is
    // not a celebration).
    if (!outcome) {
      const reason = game.terminal.reason?.replace(/_/g, ' ');
      return (
        <Box sx={{ maxWidth: 640, mx: 'auto', p: { xs: 2, sm: 3 } }}>
          <CenterCard>
            <CardTitle>Game aborted</CardTitle>
            {reason && (
              <Typography sx={{ color: LIVE_INK_SOFT }}>{reason}</Typography>
            )}
          </CenterCard>
          <ReviewBoard fen={game.fen} orientation={game.orientation} />
        </Box>
      );
    }

    // A real result: board reviewable underneath, celebratory modal on top.
    return (
      <GameSurface>
        <Box
          sx={{
            position: 'relative',
            zIndex: 1,
            maxWidth: 560,
            mx: 'auto',
            borderRadius: '20px',
            overflow: 'hidden',
            border: 'solid rgba(255,255,255,.95)',
            borderWidth: { xs: '3px', sm: '5px' },
            boxShadow: `0 16px 40px ${LIVE_PLAY_THEME.deep}59`,
            lineHeight: 0,
          }}
        >
          <ChessgroundBoard fen={game.fen} orientation={game.orientation} movable={false} viewOnly />
        </Box>
        <LiveGameEndModal
          outcome={outcome.outcome}
          resigned={outcome.resigned}
          opponentName="Opponent"
          myColor={game.myColor}
          initialSec={game.initialSec}
          incrementSec={game.incrementSec}
          open={modalOpen}
          onClose={() => setModalOpen(false)}
        />
      </GameSurface>
    );
  }

  // ── Lobby (creator waiting on a challenge) ──────────────────────────────────
  if (game.status === 'challenge' && game.isCreator) {
    return (
      <CenterCard>
        <CardTitle>Waiting for your opponent…</CardTitle>
        <Typography sx={{ color: LIVE_INK_SOFT, mb: 3 }}>
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
              borderRadius: '12px',
              bgcolor: LIVE_PLAY_THEME.tint,
              border: `1px solid ${LIVE_PLAY_THEME.main}`,
              fontFamily: 'monospace',
              fontSize: 13,
              color: LIVE_INK,
              maxWidth: '100%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {inviteUrl}
          </Box>
          <PrimaryPill onClick={copyLink} testId="copy-link">
            {copied ? 'Copied!' : 'Copy link'}
          </PrimaryPill>
        </Box>
        <Typography sx={{ display: 'block', mt: 3, fontSize: 13, color: '#8A97AD' }}>
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
        <CardTitle>You&apos;ve been challenged!</CardTitle>
        <Typography sx={{ color: LIVE_INK_SOFT, mb: 3 }}>
          {tcLabel(game.initialSec, game.incrementSec)} · the creator plays {creatorColor}.
        </Typography>
        {game.error && game.error !== 'not_found' && (
          <Typography sx={{ color: '#C62828', mb: 2, fontWeight: 700 }}>
            Could not join: {game.error.replace(/_/g, ' ')}
          </Typography>
        )}
        <PrimaryPill onClick={accept} disabled={accepting} testId="accept-challenge">
          {accepting ? 'Joining…' : 'Accept & play'}
        </PrimaryPill>
      </CenterCard>
    );
  }

  // ── Playing (active board) ──────────────────────────────────────────────────
  const opponentClock = game.orientation === 'white' ? game.clocks.blackMs : game.clocks.whiteMs;
  const myClock = game.orientation === 'white' ? game.clocks.whiteMs : game.clocks.blackMs;

  return (
    <GameSurface>
      <Box
        sx={{
          position: 'relative',
          zIndex: 1,
          display: 'grid',
          gap: 2,
          alignItems: 'start',
          justifyContent: { md: 'center' },
          gridTemplateColumns: { xs: '1fr', md: 'auto 320px' },
          gridTemplateAreas: {
            xs: '"header" "board" "dock"',
            md: '"board header" "board dock"',
          },
        }}
      >
        <Box sx={{ gridArea: 'header' }}>
          <LiveGameHeader
            opponentName="Opponent"
            connected={game.opponentConnected}
            clock={fmtClock(opponentClock)}
            clockActive={!game.isMyTurn}
          />
          {!game.opponentConnected && (
            <Box
              data-testid="opponent-disconnected"
              sx={{
                mt: 1,
                px: 1.5,
                py: 1,
                borderRadius: '12px',
                bgcolor: '#FFF4E5',
                border: '1px solid #FFE0B2',
                color: '#8A5A00',
                fontFamily: nunito.style.fontFamily,
                fontWeight: 700,
                fontSize: 13,
                textAlign: 'center',
              }}
            >
              Opponent disconnected — their clock keeps running.
            </Box>
          )}
        </Box>

        <Box
          sx={{
            gridArea: 'board',
            borderRadius: '20px',
            overflow: 'hidden',
            border: 'solid rgba(255,255,255,.95)',
            borderWidth: { xs: '3px', sm: '5px' },
            boxShadow: `0 16px 40px ${LIVE_PLAY_THEME.deep}59`,
            lineHeight: 0,
          }}
        >
          <ChessgroundBoard
            fen={game.fen}
            orientation={game.orientation}
            onMove={handleMove}
            movable={game.isMyTurn}
          />
        </Box>

        <Box sx={{ gridArea: 'dock' }}>
          <LiveGameDock
            playerColor={game.orientation}
            clock={fmtClock(myClock)}
            clockActive={game.isMyTurn}
            drawOfferedByMe={game.drawOffer.fromMe}
            drawOfferedByOpponent={game.drawOffer.fromOpponent}
            canAbort={game.canAbort}
            onAbort={() => void game.abort()}
            onOfferDraw={() => void game.offerDraw()}
            onAcceptDraw={() => void game.acceptDraw()}
            onDeclineDraw={() => void game.declineDraw()}
            onResign={() => void game.resign()}
          />
          <MoveList moves={game.moves} />
        </Box>
      </Box>
    </GameSurface>
  );
}

/** The in-game screen: world scenery gradient behind a rounded surface. */
function GameSurface({ children }: { children: React.ReactNode }) {
  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', p: { xs: 1, sm: 3 } }}>
      <Box
        sx={{
          position: 'relative',
          overflow: 'hidden',
          borderRadius: '24px',
          p: { xs: 1.5, sm: 3 },
        }}
      >
        <WorldScenery tier="beginner" />
        {children}
      </Box>
    </Box>
  );
}

/** View-only board used on an aborted-game review screen. */
function ReviewBoard({ fen, orientation }: { fen: string; orientation: 'white' | 'black' }) {
  return (
    <Box
      sx={{
        maxWidth: 520,
        mx: 'auto',
        mt: 1,
        borderRadius: '16px',
        overflow: 'hidden',
        lineHeight: 0,
      }}
    >
      <ChessgroundBoard fen={fen} orientation={orientation} movable={false} viewOnly />
    </Box>
  );
}

function MoveList({
  moves,
}: {
  moves: Array<{ ply: number; san: string | null; uci: string }>;
}) {
  if (moves.length === 0) return null;
  return (
    <Box
      sx={{
        mt: 2,
        p: 1.5,
        borderRadius: '18px',
        bgcolor: 'rgba(255,255,255,.95)',
        boxShadow: `0 10px 26px ${LIVE_PLAY_THEME.deep}33`,
        fontFamily: nunito.style.fontFamily,
      }}
    >
      <Typography
        sx={{ fontWeight: 900, fontSize: 12, color: LIVE_INK_SOFT, mb: 0.5, letterSpacing: 0.5 }}
      >
        MOVES
      </Typography>
      <Box
        sx={{
          maxHeight: 300,
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
              <Box sx={{ fontWeight: 700, color: LIVE_INK }}>{white?.san ?? white?.uci ?? ''}</Box>
              <Box sx={{ fontWeight: 700, color: LIVE_INK }}>{black?.san ?? black?.uci ?? ''}</Box>
            </React.Fragment>
          );
        })}
      </Box>
    </Box>
  );
}
