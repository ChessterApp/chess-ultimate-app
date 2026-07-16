/**
 * Pure state model for `useLiveGame` (phase 3). No React, no I/O — every
 * transition is a plain reducer and every piece of exposed UI state is a
 * selector, so the whole thing is unit-testable without a live socket.
 *
 * Postgres is truth: `hydrate` (from `GET /api/live-games/[gameId]`) seeds the whole
 * state; broadcast events (`game.start` / `game.move` / `game.end`) are applied
 * on top and are always idempotent — a stale or duplicate event never rewinds
 * the game. On any Realtime reconnect the hook re-hydrates, so this reducer only
 * has to be monotonic, not perfectly ordered.
 */

import { remainingMs } from '@/lib/live-game/clocks';
import { turnFromFen } from '@/lib/live-game/validate';
import type {
  GameStatus,
  ColorChoice,
  Turn,
  Clocks,
  HydrationPayload,
  GameStartPayload,
  GameMovePayload,
  GameEndPayload,
  GameDrawOfferPayload,
  GameDrawDeclinePayload,
} from '@/lib/live-game/types';

/** A single played move, as accumulated from hydration + broadcasts. */
export interface MoveEntry {
  ply: number;
  uci: string;
  san: string | null;
  fenAfter: string | null;
}

/** The reducer's internal state. `clockFrom` is the client-side epoch-ms
 * baseline at which `whiteMs`/`blackMs` were last authoritative — the cosmetic
 * countdown ticks the side-to-move down from here (never authoritative). */
export interface LiveGameState {
  status: GameStatus;
  fen: string;
  ply: number;
  whiteMs: number | null;
  blackMs: number | null;
  clockFrom: number | null;
  colorChoice: ColorChoice;
  initialSec: number | null;
  incrementSec: number | null;
  creatorId: string;
  whiteId: string | null;
  blackId: string | null;
  opponentId: string | null;
  result: string | null;
  winnerId: string | null;
  endReason: string | null;
  /** Clerk id of the player with a standing draw offer, or null. */
  drawOfferBy: string | null;
  moves: MoveEntry[];
}

export type LiveGameAction =
  | { type: 'hydrate'; payload: HydrationPayload; at: number }
  | { type: 'start'; payload: GameStartPayload; at: number }
  | { type: 'move'; payload: GameMovePayload; at: number }
  | { type: 'end'; payload: GameEndPayload; at: number }
  | { type: 'draw_offer'; payload: GameDrawOfferPayload; at: number }
  | { type: 'draw_decline'; payload: GameDrawDeclinePayload; at: number };

/** Empty starting state before the first hydration lands. */
export function emptyLiveGameState(): LiveGameState {
  return {
    status: 'challenge',
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    ply: 0,
    whiteMs: null,
    blackMs: null,
    clockFrom: null,
    colorChoice: 'random',
    initialSec: null,
    incrementSec: null,
    creatorId: '',
    whiteId: null,
    blackId: null,
    opponentId: null,
    result: null,
    winnerId: null,
    endReason: null,
    drawOfferBy: null,
    moves: [],
  };
}

/** Terminal statuses — no further moves are accepted. */
const TERMINAL: ReadonlySet<GameStatus> = new Set([
  'finished',
  'aborted',
  'expired',
]);

/** Winner id implied by a result string, given resolved player identities. */
function winnerFromResult(
  result: string | null,
  whiteId: string | null,
  blackId: string | null,
): string | null {
  if (result === '1-0') return whiteId;
  if (result === '0-1') return blackId;
  return null; // draw or unknown
}

export function liveGameReducer(
  state: LiveGameState,
  action: LiveGameAction,
): LiveGameState {
  switch (action.type) {
    case 'hydrate': {
      const g = action.payload.game;
      return {
        status: g.status,
        fen: g.fen,
        ply: g.ply,
        whiteMs: g.whiteMs,
        blackMs: g.blackMs,
        clockFrom: action.at,
        colorChoice: g.colorChoice,
        initialSec: g.initialSec,
        incrementSec: g.incrementSec,
        creatorId: g.creatorId,
        whiteId: g.whiteId ?? null,
        blackId: g.blackId ?? null,
        opponentId: g.opponentId ?? null,
        result: g.result,
        winnerId: g.winnerId,
        endReason: g.endReason,
        drawOfferBy: g.drawOfferBy ?? null,
        moves: action.payload.moves.map((m) => ({
          ply: m.ply,
          uci: m.uci,
          san: m.san,
          fenAfter: m.fenAfter,
        })),
      };
    }

    case 'start': {
      // Idempotent: once the game is active (or over) a replayed start is a
      // no-op beyond refreshing player identities/clocks it already agrees on.
      if (TERMINAL.has(state.status)) return state;
      const p = action.payload;
      return {
        ...state,
        status: p.status,
        fen: p.fen,
        whiteId: p.whiteId,
        blackId: p.blackId,
        whiteMs: p.whiteMs,
        blackMs: p.blackMs,
        clockFrom: action.at,
      };
    }

    case 'move': {
      const p = action.payload;
      // Only accept the strict next ply — duplicates and out-of-order events
      // are dropped (a reconnect re-hydration fills any real gap).
      if (p.ply !== state.ply + 1) return state;
      const nextMoves = [
        ...state.moves,
        { ply: p.ply, uci: p.uci, san: p.san, fenAfter: p.fenAfter },
      ];
      const base: LiveGameState = {
        ...state,
        fen: p.fenAfter,
        ply: p.ply,
        whiteMs: p.whiteMs,
        blackMs: p.blackMs,
        clockFrom: action.at,
        // A move clears any standing draw offer (mirrors the move route).
        drawOfferBy: null,
        moves: nextMoves,
      };
      if (p.gameOver) {
        return {
          ...base,
          status: 'finished',
          result: p.gameOver.result,
          endReason: p.gameOver.reason,
          winnerId: winnerFromResult(
            p.gameOver.result,
            state.whiteId,
            state.blackId,
          ),
        };
      }
      return base;
    }

    case 'end': {
      const p = action.payload;
      return {
        ...state,
        // 'finished' for resign/draw/flag/mate, 'aborted' for abort.
        status: p.status ?? 'finished',
        result: p.result,
        winnerId: p.winnerId,
        endReason: p.reason,
        whiteMs: p.whiteMs,
        blackMs: p.blackMs,
        drawOfferBy: null,
        clockFrom: action.at,
      };
    }

    case 'draw_offer': {
      // Ignore stale offers once the game is terminal.
      if (TERMINAL.has(state.status)) return state;
      return { ...state, drawOfferBy: action.payload.by };
    }

    case 'draw_decline': {
      return { ...state, drawOfferBy: null };
    }

    default:
      return state;
  }
}

// ─── Selectors (derived, view-facing) ────────────────────────────────────────

export type PlayerColor = 'white' | 'black';

/** Whose move it is, straight from the FEN. */
export function deriveTurn(state: LiveGameState): Turn {
  return turnFromFen(state.fen);
}

/**
 * This viewer's colour, or null if unknown. Known once identities are resolved
 * (game left 'challenge'); before that the creator's `colorChoice` is a hint
 * for a concrete white/black pick only (random stays unknown → orient white).
 */
export function deriveMyColor(
  state: LiveGameState,
  userId: string | null,
): PlayerColor | null {
  if (!userId) return null;
  if (state.whiteId === userId) return 'white';
  if (state.blackId === userId) return 'black';
  if (userId === state.creatorId) {
    if (state.colorChoice === 'white') return 'white';
    if (state.colorChoice === 'black') return 'black';
  }
  return null;
}

/** Board orientation for this viewer — defaults to white when colour unknown. */
export function deriveOrientation(
  state: LiveGameState,
  userId: string | null,
): PlayerColor {
  return deriveMyColor(state, userId) ?? 'white';
}

/** True only when the game is active and it is this viewer's turn to move. */
export function deriveIsMyTurn(
  state: LiveGameState,
  userId: string | null,
): boolean {
  if (state.status !== 'active') return false;
  const mine = deriveMyColor(state, userId);
  if (!mine) return false;
  return deriveTurn(state) === (mine === 'white' ? 'w' : 'b');
}

/** True when the viewer created this game (owns the lobby / copy-link screen). */
export function deriveIsCreator(
  state: LiveGameState,
  userId: string | null,
): boolean {
  return !!userId && userId === state.creatorId;
}

/** Cosmetic clock projection at `now` — ticks the side-to-move down from the
 * last authoritative banks. Never authoritative; the server owns real time. */
export function deriveClocks(state: LiveGameState, now: number): Clocks {
  return remainingMs(
    {
      whiteMs: state.whiteMs,
      blackMs: state.blackMs,
      lastMoveAt: state.clockFrom,
      turn: deriveTurn(state),
      status: state.status,
    },
    now,
  );
}

export interface TerminalInfo {
  isOver: boolean;
  /** '1-0' | '0-1' | '1/2-1/2' | null */
  result: string | null;
  /** 'win' | 'loss' | 'draw' from this viewer's POV, null while in play. */
  outcome: 'win' | 'loss' | 'draw' | null;
  winnerId: string | null;
  reason: string | null;
}

/** Map terminal DB state to a viewer-relative win/loss/draw verdict. */
export function deriveTerminal(
  state: LiveGameState,
  userId: string | null,
): TerminalInfo {
  const isOver = TERMINAL.has(state.status);
  if (!isOver) {
    return {
      isOver: false,
      result: null,
      outcome: null,
      winnerId: null,
      reason: null,
    };
  }
  let outcome: 'win' | 'loss' | 'draw' | null = null;
  if (state.result === '1/2-1/2') {
    outcome = 'draw';
  } else if (state.winnerId) {
    outcome = state.winnerId === userId ? 'win' : 'loss';
  }
  return {
    isOver: true,
    result: state.result,
    outcome,
    winnerId: state.winnerId,
    reason: state.endReason,
  };
}

export interface DrawOfferInfo {
  /** True when there is any standing draw offer (from either side). */
  pending: boolean;
  /** True when this viewer is the one who offered (awaiting a reply). */
  fromMe: boolean;
  /** True when the opponent offered and this viewer must accept/decline. */
  fromOpponent: boolean;
}

/** Draw-offer state from this viewer's POV — only meaningful while active. */
export function deriveDrawOffer(
  state: LiveGameState,
  userId: string | null,
): DrawOfferInfo {
  const by = state.status === 'active' ? state.drawOfferBy : null;
  if (!by) return { pending: false, fromMe: false, fromOpponent: false };
  const fromMe = !!userId && by === userId;
  return { pending: true, fromMe, fromOpponent: !fromMe };
}

/**
 * Auto-flag detection (pure so it's unit-testable). Returns the side that has
 * flagged — i.e. the side to move whose cosmetic bank has reached 0 at `now` —
 * or null. Only fires for an active, timed game. The hook uses this to fire a
 * single guarded `claimFlag()`; the server re-verifies before ending the game.
 */
export function deriveAutoFlag(
  state: LiveGameState,
  now: number,
): Turn | null {
  if (state.status !== 'active') return null;
  if (state.whiteMs === null || state.blackMs === null) return null; // untimed
  const turn = deriveTurn(state);
  const clocks = deriveClocks(state, now);
  const bank = turn === 'w' ? clocks.whiteMs : clocks.blackMs;
  return bank !== null && bank <= 0 ? turn : null;
}
