import { describe, it, expect } from 'vitest';
import type { GameResult } from '@/types/coach';
import { engineLineActions, gameToOpen, puzzleAction, resultToGame } from '../card-actions';
import type { EngineLineSummary } from '../tool-summary';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const OTHER = '8/8/8/8/8/8/8/K6k w - - 0 1';
const line = (san: string[]): EngineLineSummary => ({ kind: 'engine_line', fen: START, eval_cp: 30, lines: [{ san, eval_cp: 30 }] });

describe('engineLineActions', () => {
  it('draws the first three plies as arrows on the same position', () => {
    expect(engineLineActions(line(['e4', 'e5', 'Nf3', 'Nc6']), START)).toEqual([
      {
        type: 'draw_arrows',
        arrows: [
          { from: 'e2', to: 'e4', brush: 'green' },
          { from: 'e7', to: 'e5', brush: 'blue' },
          { from: 'g1', to: 'f3', brush: 'yellow' },
        ],
      },
    ]);
  });

  it('puts the position up first when the board shows another one', () => {
    const actions = engineLineActions(line(['e4']), OTHER);
    expect(actions.map((a) => a.type)).toEqual(['set_fen', 'draw_arrows']);
  });

  it('stops at a move that does not fit, nothing when none does', () => {
    const actions = engineLineActions(line(['e4', 'Qh8']), START);
    expect(actions[0].type === 'draw_arrows' && actions[0].arrows.length).toBe(1);
    expect(engineLineActions(line(['Qh8']), START)).toEqual([]);
  });
});

describe('puzzleAction', () => {
  const summary = { kind: 'puzzle' as const, puzzle_id: 'p1', fen: START };
  it('finds the turn’s set_puzzle by id, or by position without one', () => {
    const byId = { type: 'set_puzzle' as const, fen: OTHER, solution: ['a1a2'], puzzle_id: 'p1' };
    expect(puzzleAction(summary, [{ type: 'flip_board' }, byId])).toBe(byId);
    const byFen = { type: 'set_puzzle' as const, fen: START, solution: ['e2e4'] };
    expect(puzzleAction(summary, [byFen])).toBe(byFen);
    expect(puzzleAction(summary, [{ ...byId, puzzle_id: 'p2' }])).toBeNull();
    expect(puzzleAction(summary, undefined)).toBeNull();
  });
});

describe('game cards', () => {
  const card: GameResult = {
    id: 'g1', white_name: 'me', black_name: 'you', result: '1-0', date: '2024.05.01', eco: 'C20',
    opening: '', event: '', white_elo: null, black_elo: 1500, source: 'user', pgn: '1. e4 1-0',
  };

  it('opens the turn’s own card (with its PGN) when the id matches', () => {
    expect(gameToOpen({ id: 'g1', white: 'me', black: 'you', result: '1-0' }, [card])).toBe(card);
  });

  it('builds a master-database card otherwise; no id, nothing to open', () => {
    expect(gameToOpen({ id: 7, white: 'A', black: 'B', result: '0-1', year: 1999 }, [card])).toMatchObject({
      id: 7, white_name: 'A', black_name: 'B', date: '1999', white_elo: null,
    });
    expect(gameToOpen({ white: 'A', black: 'B', result: '*' }, [card])).toBeNull();
  });

  it('maps a game_results card to the list shape', () => {
    expect(resultToGame(card)).toEqual({ id: 'g1', white: 'me', black: 'you', result: '1-0', eco: 'C20', year: 2024, white_elo: undefined, black_elo: 1500 });
  });
});
