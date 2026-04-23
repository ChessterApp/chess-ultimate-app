import { describe, it, expect } from 'vitest';
import type {
  BoardAction,
  CoachResponse,
  CoachSession,
  PuzzleState,
  CoachBoardState,
  SetFenAction,
  LoadPgnAction,
  SetPuzzleAction,
  DrawArrowsAction,
  HighlightSquaresAction,
  NavigateAction,
  FlipBoardAction,
  ClearBoardAction,
} from '../coach';

describe('Coach Types', () => {
  it('BoardAction union covers all 8 action types', () => {
    const actions: BoardAction[] = [
      { type: 'set_fen', fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1' },
      { type: 'load_pgn', pgn: '1. e4 e5' },
      { type: 'set_puzzle', fen: 'start', solution: ['e2e4'] },
      { type: 'draw_arrows', arrows: [{ from: 'e2', to: 'e4', brush: 'green' }] },
      { type: 'highlight_squares', squares: ['d5'], color: 'yellow' },
      { type: 'navigate', move_index: 5 },
      { type: 'flip_board' },
      { type: 'clear_board' },
    ];

    expect(actions).toHaveLength(8);
    const types = actions.map((a) => a.type);
    expect(types).toContain('set_fen');
    expect(types).toContain('load_pgn');
    expect(types).toContain('set_puzzle');
    expect(types).toContain('draw_arrows');
    expect(types).toContain('highlight_squares');
    expect(types).toContain('navigate');
    expect(types).toContain('flip_board');
    expect(types).toContain('clear_board');
  });

  it('CoachResponse structure matches board_protocol', () => {
    const response: CoachResponse = {
      message: 'This is a strong position for white.',
      board_actions: [
        { type: 'draw_arrows', arrows: [{ from: 'g1', to: 'f3', brush: 'green' }] },
        { type: 'highlight_squares', squares: ['d5'], color: 'yellow' },
      ],
    };

    expect(response.message).toBeDefined();
    expect(response.board_actions).toHaveLength(2);
  });

  it('PuzzleState tracks solution progress', () => {
    const puzzle: PuzzleState = {
      fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      solution: ['e7e5', 'g1f3'],
      currentMoveIndex: 0,
      solved: false,
    };

    expect(puzzle.solution).toHaveLength(2);
    expect(puzzle.solved).toBe(false);
    expect(puzzle.currentMoveIndex).toBe(0);
  });
});
