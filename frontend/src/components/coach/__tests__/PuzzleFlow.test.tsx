/**
 * @vitest-environment jsdom
 *
 * The puzzle panel's steps over the board hook (tester, 18.11): in a multi-move puzzle the steps are the student's
 * moves only, the opponent's replies are played by the board, and the student never gets to move the opponent's
 * pieces.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCoachBoard, PUZZLE_REPLY_DELAY_MS } from '@/hooks/useCoachBoard';
import { usePuzzleStep } from '../PuzzleFlow';

// Black to move: …Nc6, Bb5 (the board's reply), …a6.
const BLACK_FEN = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2';
const LINE = ['Nc6', 'Bb5', 'a6'];

function setup(fen = BLACK_FEN, solution = LINE) {
  const hook = renderHook(() => {
    const board = useCoachBoard();
    const step = usePuzzleStep(board.puzzleState, board.fen, board.validatePuzzleMove, board.playPuzzleReply);
    return { board, step };
  });
  act(() => {
    hook.result.current.board.applyBoardAction({ type: 'set_puzzle', fen, solution });
  });
  return hook;
}

async function play(hook: ReturnType<typeof setup>, from: string, to: string) {
  act(() => hook.result.current.step.move(from, to));
  await act(async () => {
    hook.result.current.step.check();
  });
}

describe('usePuzzleStep on a multi-move puzzle', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('counts only the student moves', () => {
    const hook = setup();
    expect(hook.result.current.step.flow.state).toMatchObject({ index: 0, total: 2, phase: 'idle' });
    expect(hook.result.current.board.orientation).toBe('black');
  });

  it('plays the reply itself; the next step is the student move after it', async () => {
    const hook = setup();
    await play(hook, 'b8', 'c6');
    expect(hook.result.current.step.flow.state.phase).toBe('correct');
    expect(hook.result.current.step.boardLocked).toBe(true);

    act(() => { vi.advanceTimersByTime(PUZZLE_REPLY_DELAY_MS); });
    expect(hook.result.current.board.fen).toMatch(/\/1B2p3\/.* b /);
    // The move strip's history: the student's move and the reply.
    expect(hook.result.current.board.fens).toHaveLength(3);

    act(() => hook.result.current.step.next());
    expect(hook.result.current.step.flow.state).toMatchObject({ index: 1, total: 2, phase: 'idle' });
    expect(hook.result.current.step.boardLocked).toBe(false);

    await play(hook, 'a7', 'a6');
    expect(hook.result.current.step.flow.state).toMatchObject({ index: 1, phase: 'correct' });
    expect(hook.result.current.board.puzzleState?.solved).toBe(true);
  });

  it('«Дальше» before the pause ran out plays the reply at once', async () => {
    const hook = setup();
    await play(hook, 'b8', 'c6');
    act(() => hook.result.current.step.next());
    expect(hook.result.current.board.fens).toHaveLength(3);
    expect(hook.result.current.board.puzzleState?.currentMoveIndex).toBe(2);
    expect(hook.result.current.step.flow.state).toMatchObject({ index: 1, phase: 'idle' });
    act(() => { vi.advanceTimersByTime(2000); });
    expect(hook.result.current.board.fens).toHaveLength(3);
  });

  it('never takes a move of the opponent’s pieces', async () => {
    const hook = setup();
    act(() => hook.result.current.step.move('f3', 'g5')); // White's knight: not the student's
    expect(hook.result.current.step.flow.state.phase).toBe('idle');

    await play(hook, 'b8', 'c6');
    act(() => { vi.advanceTimersByTime(PUZZLE_REPLY_DELAY_MS); });
    act(() => hook.result.current.step.next());
    act(() => hook.result.current.step.move('b5', 'c6')); // the reply's bishop
    expect(hook.result.current.step.flow.state.phase).toBe('idle');
  });

  it('a one-move puzzle is one step, solved by its move, nothing played after it', async () => {
    const hook = setup('r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4', ['Qxf7#']);
    expect(hook.result.current.step.flow.state).toMatchObject({ total: 1 });
    expect(hook.result.current.board.orientation).toBe('white');
    await play(hook, 'h5', 'f7');
    expect(hook.result.current.step.flow.state.phase).toBe('correct');
    expect(hook.result.current.board.puzzleState?.solved).toBe(true);
    act(() => { vi.advanceTimersByTime(2000); });
    expect(hook.result.current.board.fens).toHaveLength(2);
  });
});
