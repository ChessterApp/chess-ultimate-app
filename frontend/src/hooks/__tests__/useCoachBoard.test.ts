/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCoachBoard, resolveSolutionMove } from '../useCoachBoard';

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

  it('builds a navigable history from manual moves', () => {
    const { result } = renderHook(() => useCoachBoard());

    // Play e2-e4, then e7-e5 via manual piece moves
    act(() => {
      result.current.setFenFromMove('e2', 'e4');
    });
    act(() => {
      result.current.setFenFromMove('e7', 'e5');
    });

    const tipFen = result.current.fen;
    expect(result.current.moveIndex).toBe(2);
    expect(tipFen).not.toBe(DEFAULT_FEN);

    // First returns to the start position
    act(() => {
      result.current.firstMove();
    });
    expect(result.current.moveIndex).toBe(0);
    expect(result.current.fen).toBe(DEFAULT_FEN);

    // Last returns to the tip
    act(() => {
      result.current.lastMove();
    });
    expect(result.current.moveIndex).toBe(2);
    expect(result.current.fen).toBe(tipFen);
  });

  it('round-trips prev then next on manual history', () => {
    const { result } = renderHook(() => useCoachBoard());

    act(() => {
      result.current.setFenFromMove('e2', 'e4');
    });
    act(() => {
      result.current.setFenFromMove('e7', 'e5');
    });

    const tipFen = result.current.fen;

    act(() => {
      result.current.prevMove();
    });
    expect(result.current.moveIndex).toBe(1);
    const midFen = result.current.fen;
    expect(midFen).not.toBe(tipFen);
    expect(midFen).not.toBe(DEFAULT_FEN);

    act(() => {
      result.current.nextMove();
    });
    expect(result.current.moveIndex).toBe(2);
    expect(result.current.fen).toBe(tipFen);
  });

  it('truncates forward history when playing after prevMove', () => {
    const { result } = renderHook(() => useCoachBoard());

    act(() => {
      result.current.setFenFromMove('e2', 'e4');
    });
    act(() => {
      result.current.setFenFromMove('e7', 'e5');
    });

    // Step back to after 1. e4 (black to move)
    act(() => {
      result.current.prevMove();
    });
    expect(result.current.moveIndex).toBe(1);

    // Play a different black move — forward history (old e5) should be discarded
    act(() => {
      result.current.setFenFromMove('c7', 'c5');
    });

    // History is now [start, e4, c5] — no orphan future FEN
    expect(result.current.moveIndex).toBe(2);
    const tipFen = result.current.fen;

    act(() => {
      result.current.nextMove();
    });
    // Already at tip; nothing beyond it
    expect(result.current.moveIndex).toBe(2);
    expect(result.current.fen).toBe(tipFen);
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

  it('validates puzzle moves written in SAN (how Hermes sends them)', () => {
    const { result } = renderHook(() => useCoachBoard());
    // Scholar's mate: white to play Qxf7#
    const puzzleFen = 'r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4';

    act(() => {
      result.current.applyBoardAction({
        type: 'set_puzzle',
        fen: puzzleFen,
        solution: ['Qxf7#'],
      });
    });

    let moveResult: string;
    act(() => {
      moveResult = result.current.validatePuzzleMove('h5', 'h7');
    });
    expect(moveResult!).toBe('wrong');
    expect(result.current.fen).toBe(puzzleFen);

    act(() => {
      moveResult = result.current.validatePuzzleMove('h5', 'f7');
    });
    expect(moveResult!).toBe('solved');
    expect(result.current.fen).toContain('r1bqkb1r/pppp1Qpp');
  });

  it('walks a multi-move SAN solution', () => {
    const { result } = renderHook(() => useCoachBoard());
    const puzzleFen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

    act(() => {
      result.current.applyBoardAction({ type: 'set_puzzle', fen: puzzleFen, solution: ['e4', 'e5'] });
    });

    let r: string;
    act(() => { r = result.current.validatePuzzleMove('e2', 'e4'); });
    expect(r!).toBe('correct');
    act(() => { r = result.current.validatePuzzleMove('e7', 'e5'); });
    expect(r!).toBe('solved');
  });

  it('applies load_pgn followed by navigate in the same batch', () => {
    const { result } = renderHook(() => useCoachBoard());

    // Hermes sends every board action of a turn in one frame; the navigate
    // must act on the PGN loaded a moment earlier, not on the stale closure.
    act(() => {
      result.current.applyBoardActions([
        { type: 'load_pgn', pgn: '1. e4 e5 2. Nf3 Nc6' },
        { type: 'navigate', direction: 'first' },
        { type: 'navigate', direction: 'next' },
      ]);
    });

    expect(result.current.moveIndex).toBe(1);
    expect(result.current.fen).toMatch(/^rnbqkbnr\/pppppppp\/8\/8\/4P3\/8\/PPPP1PPP\/RNBQKBNR b KQkq/);
  });

  it('set_fen after load_pgn replaces the history', () => {
    const { result } = renderHook(() => useCoachBoard());
    const fen = '8/8/8/4k3/8/8/8/4K2R w - - 0 1';

    act(() => {
      result.current.applyBoardActions([
        { type: 'load_pgn', pgn: '1. e4 e5 2. Nf3 Nc6' },
        { type: 'set_fen', fen },
        { type: 'navigate', direction: 'prev' },
      ]);
    });

    expect(result.current.fen).toBe(fen);
    expect(result.current.moveIndex).toBe(0);
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

describe('resolveSolutionMove', () => {
  const fen = 'r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4';

  it('accepts SAN with or without suffixes', () => {
    expect(resolveSolutionMove(fen, 'Qxf7#')).toMatchObject({ from: 'h5', to: 'f7' });
    expect(resolveSolutionMove(fen, 'Qxf7')).toMatchObject({ from: 'h5', to: 'f7' });
    expect(resolveSolutionMove(fen, 'Qf7')).toMatchObject({ from: 'h5', to: 'f7' });
  });

  it('accepts UCI', () => {
    expect(resolveSolutionMove(fen, 'h5f7')).toMatchObject({ from: 'h5', to: 'f7', san: 'Qxf7#' });
  });

  it('rejects illegal or empty moves', () => {
    expect(resolveSolutionMove(fen, 'Qh8')).toBeNull();
    expect(resolveSolutionMove(fen, 'a1a8')).toBeNull();
    expect(resolveSolutionMove(fen, '')).toBeNull();
  });
});
