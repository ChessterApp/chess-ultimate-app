/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCoachBoard } from '../useCoachBoard';

const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('useCoachBoard', () => {
  it('initializes with default state', () => {
    const { result } = renderHook(() => useCoachBoard());

    expect(result.current.fen).toBe(DEFAULT_FEN);
    expect(result.current.pgn).toBe('');
    expect(result.current.moveIndex).toBe(-1);
    expect(result.current.arrows).toEqual([]);
    expect(result.current.highlights).toEqual([]);
    expect(result.current.orientation).toBe('white');
    expect(result.current.puzzleMode).toBe(false);
    expect(result.current.puzzleState).toBeNull();
  });

  it('applies set_fen action', () => {
    const { result } = renderHook(() => useCoachBoard());
    const testFen = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';

    act(() => {
      result.current.applyBoardAction({ type: 'set_fen', fen: testFen });
    });

    expect(result.current.fen).toBe(testFen);
    expect(result.current.arrows).toEqual([]);
    expect(result.current.puzzleMode).toBe(false);
  });

  it('applies load_pgn action', () => {
    const { result } = renderHook(() => useCoachBoard());
    const pgn = '1. e4 e5 2. Nf3 Nc6';

    act(() => {
      result.current.applyBoardAction({ type: 'load_pgn', pgn });
    });

    expect(result.current.pgn).toBe(pgn);
    // After loading PGN, should be at the last move position
    expect(result.current.fen).not.toBe(DEFAULT_FEN);
    expect(result.current.moveIndex).toBeGreaterThan(0);
  });

  it('applies set_puzzle action', () => {
    const { result } = renderHook(() => useCoachBoard());
    const puzzleFen = 'r1bqkb1r/pppppppp/2n2n2/8/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 2 3';

    act(() => {
      result.current.applyBoardAction({
        type: 'set_puzzle',
        fen: puzzleFen,
        solution: ['e4e5', 'f3d4'],
      });
    });

    expect(result.current.fen).toBe(puzzleFen);
    expect(result.current.puzzleMode).toBe(true);
    expect(result.current.puzzleState).toEqual({
      fen: puzzleFen,
      solution: ['e4e5', 'f3d4'],
      currentMoveIndex: 0,
      solved: false,
    });
  });

  it('applies draw_arrows action', () => {
    const { result } = renderHook(() => useCoachBoard());

    act(() => {
      result.current.applyBoardAction({
        type: 'draw_arrows',
        arrows: [
          { from: 'g1', to: 'f3', brush: 'green' },
          { from: 'd2', to: 'd4', brush: 'blue' },
        ],
      });
    });

    expect(result.current.arrows).toEqual([
      { from: 'g1', to: 'f3', brush: 'green' },
      { from: 'd2', to: 'd4', brush: 'blue' },
    ]);
  });

  it('applies highlight_squares action', () => {
    const { result } = renderHook(() => useCoachBoard());

    act(() => {
      result.current.applyBoardAction({
        type: 'highlight_squares',
        squares: ['d5', 'e4'],
        color: 'yellow',
      });
    });

    expect(result.current.highlights).toEqual(['d5', 'e4']);
  });

  it('applies flip_board action', () => {
    const { result } = renderHook(() => useCoachBoard());
    expect(result.current.orientation).toBe('white');

    act(() => {
      result.current.applyBoardAction({ type: 'flip_board' });
    });

    expect(result.current.orientation).toBe('black');

    act(() => {
      result.current.applyBoardAction({ type: 'flip_board' });
    });

    expect(result.current.orientation).toBe('white');
  });

  it('applies clear_board action', () => {
    const { result } = renderHook(() => useCoachBoard());

    // Set up some state first
    act(() => {
      result.current.applyBoardAction({
        type: 'set_fen',
        fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      });
      result.current.applyBoardAction({
        type: 'draw_arrows',
        arrows: [{ from: 'e2', to: 'e4', brush: 'green' }],
      });
    });

    // Now clear
    act(() => {
      result.current.applyBoardAction({ type: 'clear_board' });
    });

    expect(result.current.fen).toBe(DEFAULT_FEN);
    expect(result.current.arrows).toEqual([]);
    expect(result.current.highlights).toEqual([]);
    expect(result.current.puzzleMode).toBe(false);
  });

  it('navigates through PGN moves', () => {
    const { result } = renderHook(() => useCoachBoard());

    act(() => {
      result.current.applyBoardAction({ type: 'load_pgn', pgn: '1. e4 e5 2. Nf3 Nc6' });
    });

    const lastFen = result.current.fen;

    // Go to first
    act(() => {
      result.current.firstMove();
    });
    expect(result.current.fen).toBe(DEFAULT_FEN);
    expect(result.current.moveIndex).toBe(0);

    // Go next
    act(() => {
      result.current.nextMove();
    });
    expect(result.current.moveIndex).toBe(1);
    expect(result.current.fen).not.toBe(DEFAULT_FEN);

    // Go to last
    act(() => {
      result.current.lastMove();
    });
    expect(result.current.fen).toBe(lastFen);

    // Go prev
    act(() => {
      result.current.prevMove();
    });
    expect(result.current.moveIndex).toBeLessThan(result.current.moveIndex + 1);
  });

  it('validates puzzle moves correctly', () => {
    const { result } = renderHook(() => useCoachBoard());
    const puzzleFen = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';

    act(() => {
      result.current.applyBoardAction({
        type: 'set_puzzle',
        fen: puzzleFen,
        solution: ['e7e5'],
      });
    });

    // Wrong move
    let moveResult: string;
    act(() => {
      moveResult = result.current.validatePuzzleMove('d7', 'd5');
    });
    expect(moveResult!).toBe('wrong');

    // Correct move (and only move in solution = solved)
    act(() => {
      moveResult = result.current.validatePuzzleMove('e7', 'e5');
    });
    expect(moveResult!).toBe('solved');
    expect(result.current.puzzleState?.solved).toBe(true);
  });

  it('resets board to defaults', () => {
    const { result } = renderHook(() => useCoachBoard());

    // Set up various state
    act(() => {
      result.current.applyBoardAction({
        type: 'set_fen',
        fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
      });
      result.current.applyBoardAction({ type: 'flip_board' });
    });

    expect(result.current.orientation).toBe('black');

    act(() => {
      result.current.resetBoard();
    });

    expect(result.current.fen).toBe(DEFAULT_FEN);
    expect(result.current.orientation).toBe('white');
    expect(result.current.pgn).toBe('');
    expect(result.current.puzzleMode).toBe(false);
  });
});
