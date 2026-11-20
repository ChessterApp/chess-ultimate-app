/**
 * @vitest-environment jsdom
 *
 * Tester, 19.11: a course puzzle solved, the page opened again — the board back at the start and «Ходов пока нет».
 * A restored puzzle goes on where it was (useCoachBoard.restorePuzzleTo, replayPuzzle).
 */
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { Chess } from 'chess.js';
import { useCoachBoard, replayPuzzle, puzzleStudentMovesDone } from '../useCoachBoard';
import { initialStepFlow } from '@/lib/coach/step-flow';

const COURSE = '2r5/4kp2/3p1p2/3RpP2/1p2P2P/1P1K1QP1/r5B1/8 b - - 0 1'; // «Стоимость фигур», 1: Rc3#
const after = (fen: string, ...sans: string[]) => {
  const c = new Chess(fen);
  sans.forEach((s) => c.move(s));
  return c.fen();
};

describe('a puzzle restored with its session', () => {
  it('a solved course puzzle comes back solved, its move in the history', () => {
    const { result } = renderHook(() => useCoachBoard());
    act(() => {
      result.current.applyBoardAction({ type: 'set_puzzle', fen: COURSE, solution: ['Rc3#'] });
      result.current.restorePuzzleTo(after(COURSE, 'Rc3#'));
    });
    expect(result.current.fens).toHaveLength(2);
    expect(result.current.puzzleState?.solved).toBe(true);
    expect(puzzleStudentMovesDone(result.current.puzzleState)).toBe(1);
  });

  it('part-way: the student plays the next move; off the line or at the start: as set', () => {
    const start = '6k1/5pp1/7p/8/8/8/1Q3PPP/6K1 w - - 0 1';
    const puzzle = { fen: start, solution: ['Qb8+', 'Kh7', 'Qe5'], currentMoveIndex: 0, solved: false };
    const mid = replayPuzzle(puzzle, after(start, 'Qb8+', 'Kh7'));
    expect(mid?.fens).toHaveLength(3);
    expect(mid?.puzzle).toMatchObject({ currentMoveIndex: 2, solved: false });
    expect(puzzleStudentMovesDone(mid!.puzzle)).toBe(1);
    expect(replayPuzzle(puzzle, start)).toBeNull();
    expect(replayPuzzle(puzzle, 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')).toBeNull();
  });

  it('the steps start where the puzzle was', () => {
    expect(initialStepFlow(2, 1)).toMatchObject({ phase: 'idle', index: 1 });
    expect(initialStepFlow(1, 1)).toMatchObject({ phase: 'correct', index: 0 });
    expect(initialStepFlow(3)).toMatchObject({ phase: 'idle', index: 0 });
  });
});

describe('the board turned for a puzzle turns back when it leaves (tester 20.11)', () => {
  const BLACK_TO_MOVE = '6k1/5ppp/8/8/8/8/5PPP/r5K1 b - - 0 1';
  it('a puzzle for Black, then a position: White at the bottom again', () => {
    const { result } = renderHook(() => useCoachBoard());
    act(() => result.current.applyBoardAction({ type: 'set_puzzle', fen: BLACK_TO_MOVE, solution: ['Ra1'] }));
    expect(result.current.orientation).toBe('black');
    act(() => result.current.applyBoardAction({ type: 'set_fen', fen: COURSE }));
    expect(result.current.orientation).toBe('white');
  });
  it('the side the student had chosen before the puzzles is the one given back, after several of them', () => {
    const { result } = renderHook(() => useCoachBoard());
    act(() => result.current.setOrientation('black'));
    act(() => result.current.applyBoardAction({ type: 'set_puzzle', fen: '6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1', solution: ['Ra8#'] }));
    act(() => result.current.applyBoardAction({ type: 'set_puzzle', fen: BLACK_TO_MOVE, solution: ['Ra1'] }));
    act(() => result.current.applyBoardAction({ type: 'load_pgn', pgn: '1. e4 e5 *' }));
    expect(result.current.orientation).toBe('black');
  });
});
