import { describe, it, expect } from 'vitest';
import {
  liveGameReducer,
  emptyLiveGameState,
  deriveTurn,
  deriveMyColor,
  deriveOrientation,
  deriveIsMyTurn,
  deriveIsCreator,
  deriveClocks,
  deriveTerminal,
  type LiveGameState,
} from '../liveGameState';
import type {
  HydrationPayload,
  GameStartPayload,
  GameMovePayload,
  GameEndPayload,
} from '@/lib/live-game/types';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 =
  'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
const AFTER_E4_E5 =
  'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2';

function hydrateActive(overrides: Partial<HydrationPayload['game']> = {}): HydrationPayload {
  return {
    game: {
      id: 'g1',
      status: 'active',
      colorChoice: 'white',
      initialSec: 300,
      incrementSec: 2,
      fen: START_FEN,
      ply: 0,
      whiteMs: 300000,
      blackMs: 300000,
      result: null,
      winnerId: null,
      endReason: null,
      creatorId: 'creator',
      whiteId: 'creator',
      blackId: 'joiner',
      opponentId: 'joiner',
      ...overrides,
    },
    moves: [],
  };
}

function hydrateChallenge(overrides: Partial<HydrationPayload['game']> = {}): HydrationPayload {
  return {
    game: {
      id: 'g1',
      status: 'challenge',
      colorChoice: 'random',
      initialSec: 300,
      incrementSec: 0,
      fen: START_FEN,
      ply: 0,
      whiteMs: null,
      blackMs: null,
      result: null,
      winnerId: null,
      endReason: null,
      creatorId: 'creator',
      ...overrides,
    },
    moves: [],
  };
}

describe('liveGameReducer — hydrate', () => {
  it('seeds full state from an active hydration payload', () => {
    const s = liveGameReducer(emptyLiveGameState(), {
      type: 'hydrate',
      payload: hydrateActive(),
      at: 1000,
    });
    expect(s.status).toBe('active');
    expect(s.fen).toBe(START_FEN);
    expect(s.whiteId).toBe('creator');
    expect(s.blackId).toBe('joiner');
    expect(s.whiteMs).toBe(300000);
    expect(s.clockFrom).toBe(1000);
  });

  it('seeds a challenge with no resolved identities', () => {
    const s = liveGameReducer(emptyLiveGameState(), {
      type: 'hydrate',
      payload: hydrateChallenge(),
      at: 500,
    });
    expect(s.status).toBe('challenge');
    expect(s.whiteId).toBeNull();
    expect(s.blackId).toBeNull();
    expect(s.creatorId).toBe('creator');
  });

  it('carries move history', () => {
    const payload = hydrateActive({ ply: 1, fen: AFTER_E4 });
    payload.moves = [
      { ply: 1, uci: 'e2e4', san: 'e4', fenAfter: AFTER_E4, moveTimeMs: 1200 },
    ];
    const s = liveGameReducer(emptyLiveGameState(), {
      type: 'hydrate',
      payload,
      at: 0,
    });
    expect(s.moves).toHaveLength(1);
    expect(s.moves[0]).toEqual({ ply: 1, uci: 'e2e4', san: 'e4', fenAfter: AFTER_E4 });
  });
});

describe('liveGameReducer — start', () => {
  it('flips a challenge to active with resolved colors and clocks', () => {
    const base = liveGameReducer(emptyLiveGameState(), {
      type: 'hydrate',
      payload: hydrateChallenge(),
      at: 0,
    });
    const payload: GameStartPayload = {
      gameId: 'g1',
      status: 'active',
      fen: START_FEN,
      whiteId: 'creator',
      blackId: 'joiner',
      whiteMs: 300000,
      blackMs: 300000,
      lastMoveAt: null,
    };
    const s = liveGameReducer(base, { type: 'start', payload, at: 2000 });
    expect(s.status).toBe('active');
    expect(s.whiteId).toBe('creator');
    expect(s.blackId).toBe('joiner');
    expect(s.clockFrom).toBe(2000);
  });

  it('is a no-op once the game is terminal', () => {
    const finished: LiveGameState = { ...emptyLiveGameState(), status: 'finished' };
    const payload: GameStartPayload = {
      gameId: 'g1',
      status: 'active',
      fen: START_FEN,
      whiteId: 'a',
      blackId: 'b',
      whiteMs: 1,
      blackMs: 1,
      lastMoveAt: null,
    };
    expect(liveGameReducer(finished, { type: 'start', payload, at: 1 })).toBe(finished);
  });
});

describe('liveGameReducer — move', () => {
  const base = liveGameReducer(emptyLiveGameState(), {
    type: 'hydrate',
    payload: hydrateActive(),
    at: 0,
  });

  it('applies the strict next ply', () => {
    const payload: GameMovePayload = {
      ply: 1,
      uci: 'e2e4',
      san: 'e4',
      fenAfter: AFTER_E4,
      whiteMs: 302000,
      blackMs: 300000,
    };
    const s = liveGameReducer(base, { type: 'move', payload, at: 5000 });
    expect(s.ply).toBe(1);
    expect(s.fen).toBe(AFTER_E4);
    expect(s.moves).toHaveLength(1);
    expect(s.whiteMs).toBe(302000);
    expect(s.clockFrom).toBe(5000);
  });

  it('drops a duplicate / out-of-order ply', () => {
    const payload: GameMovePayload = {
      ply: 2,
      uci: 'e7e5',
      san: 'e5',
      fenAfter: AFTER_E4_E5,
      whiteMs: 302000,
      blackMs: 300000,
    };
    // base is at ply 0; ply 2 is not the strict next → ignored.
    expect(liveGameReducer(base, { type: 'move', payload, at: 1 })).toBe(base);
  });

  it('marks the game finished with a winner on a mating move', () => {
    const payload: GameMovePayload = {
      ply: 1,
      uci: 'e2e4',
      san: 'e4#',
      fenAfter: AFTER_E4,
      whiteMs: 302000,
      blackMs: 300000,
      gameOver: { result: '1-0', reason: 'checkmate' },
    };
    const s = liveGameReducer(base, { type: 'move', payload, at: 1 });
    expect(s.status).toBe('finished');
    expect(s.result).toBe('1-0');
    expect(s.endReason).toBe('checkmate');
    expect(s.winnerId).toBe('creator'); // white
  });

  it('maps a 0-1 result to the black player', () => {
    const payload: GameMovePayload = {
      ply: 1,
      uci: 'e2e4',
      san: 'x',
      fenAfter: AFTER_E4,
      whiteMs: 1,
      blackMs: 1,
      gameOver: { result: '0-1', reason: 'checkmate' },
    };
    const s = liveGameReducer(base, { type: 'move', payload, at: 1 });
    expect(s.winnerId).toBe('joiner'); // black
  });

  it('leaves winner null for a draw result', () => {
    const payload: GameMovePayload = {
      ply: 1,
      uci: 'e2e4',
      san: 'x',
      fenAfter: AFTER_E4,
      whiteMs: 1,
      blackMs: 1,
      gameOver: { result: '1/2-1/2', reason: 'stalemate' },
    };
    const s = liveGameReducer(base, { type: 'move', payload, at: 1 });
    expect(s.status).toBe('finished');
    expect(s.winnerId).toBeNull();
  });
});

describe('liveGameReducer — end', () => {
  it('sets terminal fields', () => {
    const base = liveGameReducer(emptyLiveGameState(), {
      type: 'hydrate',
      payload: hydrateActive(),
      at: 0,
    });
    const payload: GameEndPayload = {
      gameId: 'g1',
      result: '0-1',
      winnerId: 'joiner',
      reason: 'flag',
      whiteMs: 0,
      blackMs: 12000,
    };
    const s = liveGameReducer(base, { type: 'end', payload, at: 9000 });
    expect(s.status).toBe('finished');
    expect(s.result).toBe('0-1');
    expect(s.winnerId).toBe('joiner');
    expect(s.endReason).toBe('flag');
    expect(s.whiteMs).toBe(0);
  });
});

describe('derivations', () => {
  const active = liveGameReducer(emptyLiveGameState(), {
    type: 'hydrate',
    payload: hydrateActive(),
    at: 0,
  });

  it('deriveTurn reads the FEN active color', () => {
    expect(deriveTurn(active)).toBe('w');
    expect(deriveTurn({ ...active, fen: AFTER_E4 })).toBe('b');
  });

  it('deriveMyColor resolves from white/black ids', () => {
    expect(deriveMyColor(active, 'creator')).toBe('white');
    expect(deriveMyColor(active, 'joiner')).toBe('black');
    expect(deriveMyColor(active, 'stranger')).toBeNull();
    expect(deriveMyColor(active, null)).toBeNull();
  });

  it('deriveMyColor uses the creator color hint before identities resolve', () => {
    const chWhite = liveGameReducer(emptyLiveGameState(), {
      type: 'hydrate',
      payload: hydrateChallenge({ colorChoice: 'white' }),
      at: 0,
    });
    expect(deriveMyColor(chWhite, 'creator')).toBe('white');
    const chBlack = { ...chWhite, colorChoice: 'black' as const };
    expect(deriveMyColor(chBlack, 'creator')).toBe('black');
    const chRandom = { ...chWhite, colorChoice: 'random' as const };
    expect(deriveMyColor(chRandom, 'creator')).toBeNull();
  });

  it('deriveOrientation defaults to white when unknown', () => {
    expect(deriveOrientation(active, 'joiner')).toBe('black');
    expect(deriveOrientation(active, 'stranger')).toBe('white');
  });

  it('deriveIsMyTurn is true only when active and on move', () => {
    expect(deriveIsMyTurn(active, 'creator')).toBe(true); // white to move
    expect(deriveIsMyTurn(active, 'joiner')).toBe(false); // black waits
    const black = { ...active, fen: AFTER_E4 };
    expect(deriveIsMyTurn(black, 'joiner')).toBe(true);
    const challenge = { ...active, status: 'challenge' as const };
    expect(deriveIsMyTurn(challenge, 'creator')).toBe(false);
  });

  it('deriveIsCreator identifies the owner', () => {
    expect(deriveIsCreator(active, 'creator')).toBe(true);
    expect(deriveIsCreator(active, 'joiner')).toBe(false);
    expect(deriveIsCreator(active, null)).toBe(false);
  });
});

describe('deriveClocks (cosmetic projection)', () => {
  it('ticks the side-to-move down from the baseline', () => {
    const s: LiveGameState = {
      ...emptyLiveGameState(),
      status: 'active',
      fen: START_FEN, // white to move
      whiteMs: 300000,
      blackMs: 300000,
      clockFrom: 1000,
    };
    const c = deriveClocks(s, 1000 + 5000);
    expect(c.whiteMs).toBe(295000); // white debited 5s
    expect(c.blackMs).toBe(300000); // idle side unchanged
  });

  it('never returns negative time', () => {
    const s: LiveGameState = {
      ...emptyLiveGameState(),
      status: 'active',
      fen: START_FEN,
      whiteMs: 1000,
      blackMs: 300000,
      clockFrom: 0,
    };
    expect(deriveClocks(s, 999999).whiteMs).toBe(0);
  });

  it('returns stored banks for untimed / non-active games', () => {
    const untimed: LiveGameState = {
      ...emptyLiveGameState(),
      status: 'active',
      whiteMs: null,
      blackMs: null,
      clockFrom: 0,
    };
    expect(deriveClocks(untimed, 5000)).toEqual({ whiteMs: null, blackMs: null });

    const finished: LiveGameState = {
      ...emptyLiveGameState(),
      status: 'finished',
      whiteMs: 12000,
      blackMs: 8000,
      clockFrom: 0,
    };
    expect(deriveClocks(finished, 5000)).toEqual({ whiteMs: 12000, blackMs: 8000 });
  });
});

describe('deriveTerminal', () => {
  const finished: LiveGameState = {
    ...emptyLiveGameState(),
    status: 'finished',
    whiteId: 'creator',
    blackId: 'joiner',
    result: '1-0',
    winnerId: 'creator',
    endReason: 'checkmate',
  };

  it('reports win/loss from the viewer POV', () => {
    expect(deriveTerminal(finished, 'creator').outcome).toBe('win');
    expect(deriveTerminal(finished, 'joiner').outcome).toBe('loss');
  });

  it('reports a draw', () => {
    const draw = { ...finished, result: '1/2-1/2', winnerId: null };
    expect(deriveTerminal(draw, 'creator').outcome).toBe('draw');
    expect(deriveTerminal(draw, 'joiner').outcome).toBe('draw');
  });

  it('is not-over while the game is in play', () => {
    const active: LiveGameState = { ...emptyLiveGameState(), status: 'active' };
    const t = deriveTerminal(active, 'creator');
    expect(t.isOver).toBe(false);
    expect(t.outcome).toBeNull();
  });

  it('treats aborted / expired as terminal', () => {
    expect(deriveTerminal({ ...finished, status: 'aborted' }, 'creator').isOver).toBe(true);
    expect(deriveTerminal({ ...finished, status: 'expired' }, 'creator').isOver).toBe(true);
  });
});
