import { describe, it, expect } from 'vitest';
import {
  liveGameReducer,
  emptyLiveGameState,
  deriveDrawOffer,
  deriveAutoFlag,
  type LiveGameState,
} from '../liveGameState';
import type {
  HydrationPayload,
  GameEndPayload,
  GameMovePayload,
} from '@/lib/live-game/types';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';

function activeState(over: Partial<LiveGameState> = {}): LiveGameState {
  return {
    ...emptyLiveGameState(),
    status: 'active',
    fen: START_FEN,
    whiteId: 'creator',
    blackId: 'joiner',
    whiteMs: 300000,
    blackMs: 300000,
    clockFrom: 1000,
    ...over,
  };
}

describe('liveGameReducer — draw offers', () => {
  it('draw_offer records the offering player', () => {
    const s = liveGameReducer(activeState(), {
      type: 'draw_offer',
      payload: { gameId: 'g1', by: 'joiner' },
      at: 0,
    });
    expect(s.drawOfferBy).toBe('joiner');
  });

  it('draw_offer is ignored once the game is terminal', () => {
    const finished = activeState({ status: 'finished' });
    const s = liveGameReducer(finished, {
      type: 'draw_offer',
      payload: { gameId: 'g1', by: 'joiner' },
      at: 0,
    });
    expect(s).toBe(finished);
  });

  it('draw_decline clears the offer', () => {
    const offered = activeState({ drawOfferBy: 'joiner' });
    const s = liveGameReducer(offered, {
      type: 'draw_decline',
      payload: { gameId: 'g1' },
      at: 0,
    });
    expect(s.drawOfferBy).toBeNull();
  });

  it('a move clears any standing draw offer', () => {
    const offered = activeState({ drawOfferBy: 'joiner' });
    const payload: GameMovePayload = {
      ply: 1,
      uci: 'e2e4',
      san: 'e4',
      fenAfter: AFTER_E4,
      whiteMs: 300000,
      blackMs: 300000,
    };
    const s = liveGameReducer(offered, { type: 'move', payload, at: 5000 });
    expect(s.drawOfferBy).toBeNull();
  });

  it('hydrate seeds drawOfferBy', () => {
    const payload: HydrationPayload = {
      game: {
        id: 'g1',
        status: 'active',
        colorChoice: 'white',
        initialSec: 300,
        incrementSec: 0,
        fen: START_FEN,
        ply: 0,
        whiteMs: 300000,
        blackMs: 300000,
        result: null,
        winnerId: null,
        endReason: null,
        drawOfferBy: 'creator',
        creatorId: 'creator',
        whiteId: 'creator',
        blackId: 'joiner',
        opponentId: 'joiner',
      },
      moves: [],
    };
    const s = liveGameReducer(emptyLiveGameState(), { type: 'hydrate', payload, at: 0 });
    expect(s.drawOfferBy).toBe('creator');
  });
});

describe('liveGameReducer — end (new reasons)', () => {
  it('resign end sets a finished status with the winner', () => {
    const payload: GameEndPayload = {
      gameId: 'g1',
      result: '1-0',
      winnerId: 'creator',
      reason: 'resign',
      status: 'finished',
      whiteMs: 120000,
      blackMs: 90000,
    };
    const s = liveGameReducer(activeState(), { type: 'end', payload, at: 0 });
    expect(s.status).toBe('finished');
    expect(s.endReason).toBe('resign');
    expect(s.winnerId).toBe('creator');
  });

  it('abort end sets an aborted status with no result', () => {
    const payload: GameEndPayload = {
      gameId: 'g1',
      result: null,
      winnerId: null,
      reason: 'abort',
      status: 'aborted',
      whiteMs: 300000,
      blackMs: 300000,
    };
    const s = liveGameReducer(activeState(), { type: 'end', payload, at: 0 });
    expect(s.status).toBe('aborted');
    expect(s.result).toBeNull();
    expect(s.endReason).toBe('abort');
  });

  it('defaults to finished when the payload omits status (mate/flag/draw path)', () => {
    const payload: GameEndPayload = {
      gameId: 'g1',
      result: '0-1',
      winnerId: 'joiner',
      reason: 'flag',
      whiteMs: 0,
      blackMs: 60000,
    };
    const s = liveGameReducer(activeState(), { type: 'end', payload, at: 0 });
    expect(s.status).toBe('finished');
  });

  it('end clears a standing draw offer', () => {
    const payload: GameEndPayload = {
      gameId: 'g1',
      result: '1/2-1/2',
      winnerId: null,
      reason: 'draw',
      status: 'finished',
      whiteMs: 100000,
      blackMs: 100000,
    };
    const s = liveGameReducer(activeState({ drawOfferBy: 'creator' }), {
      type: 'end',
      payload,
      at: 0,
    });
    expect(s.drawOfferBy).toBeNull();
  });
});

describe('deriveDrawOffer', () => {
  it('reports an opponent offer as fromOpponent', () => {
    const s = activeState({ drawOfferBy: 'joiner' });
    const info = deriveDrawOffer(s, 'creator');
    expect(info).toEqual({ pending: true, fromMe: false, fromOpponent: true });
  });

  it('reports my own offer as fromMe', () => {
    const s = activeState({ drawOfferBy: 'creator' });
    const info = deriveDrawOffer(s, 'creator');
    expect(info).toEqual({ pending: true, fromMe: true, fromOpponent: false });
  });

  it('is not pending with no offer', () => {
    expect(deriveDrawOffer(activeState(), 'creator').pending).toBe(false);
  });

  it('ignores an offer once the game is no longer active', () => {
    const s = activeState({ status: 'finished', drawOfferBy: 'joiner' });
    expect(deriveDrawOffer(s, 'creator').pending).toBe(false);
  });
});

describe('deriveAutoFlag', () => {
  it('returns the side to move once its bank hits 0', () => {
    // White to move, 1s bank, baseline at 0 → flagged well before now.
    const s = activeState({ whiteMs: 1000, blackMs: 300000, clockFrom: 0 });
    expect(deriveAutoFlag(s, 60000)).toBe('w');
  });

  it('returns null while the running clock still has time', () => {
    const s = activeState({ whiteMs: 300000, blackMs: 300000, clockFrom: 0 });
    expect(deriveAutoFlag(s, 5000)).toBeNull();
  });

  it('returns null for an untimed game', () => {
    const s = activeState({ whiteMs: null, blackMs: null, clockFrom: 0 });
    expect(deriveAutoFlag(s, 999999)).toBeNull();
  });

  it('returns null when the game is not active', () => {
    const s = activeState({ status: 'finished', whiteMs: 0, blackMs: 0, clockFrom: 0 });
    expect(deriveAutoFlag(s, 999999)).toBeNull();
  });

  it('tracks black flagging after black is on the move', () => {
    const s = activeState({ fen: AFTER_E4, whiteMs: 300000, blackMs: 500, clockFrom: 0 });
    expect(deriveAutoFlag(s, 60000)).toBe('b');
  });
});
