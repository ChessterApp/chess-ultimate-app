// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React, { useEffect } from 'react';

// Stand-in board: reports a fresh (unrevealed) state on mount and exposes a
// button that reports the hint as revealed, like pressing Hint does.
const boardProps: any[] = [];
vi.mock('@/components/chess', () => ({
  AnimatedChessBoard: (props: any) => {
    boardProps.push(props);
    const report = (hintRevealed: boolean) =>
      props.onBoardStateChange({ currentFen: props.fen, attempts: 0, solved: false, hintRevealed });
    useEffect(() => report(false), []); // eslint-disable-line react-hooks/exhaustive-deps
    return <button onClick={() => report(true)}>reveal</button>;
  },
}));
vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('@/components/ToastProvider', () => ({ useToast: () => ({ showToast: vi.fn() }) }));

const PUZZLES = [
  { id: 'p1', order_index: 1, fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1', solution_move: 'a1a8', hint_text: 'Use the rook', completed: false, attempts: 0 },
  { id: 'p2', order_index: 2, fen: '4k3/8/8/8/8/8/8/1R2K3 w - - 0 1', solution_move: 'b1b8', hint_text: 'Rook again', completed: false, attempts: 0 },
];
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => ({ puzzles: PUZZLES, total_count: 2, completed_count: 0, current_index: 1 })),
  ApiError: class ApiError extends Error {},
}));

import PuzzleSequence from '../PuzzleSequence';

afterEach(() => {
  cleanup();
  boardProps.length = 0;
});

describe('PuzzleSequence hint text', () => {
  it('hides hint_text until the board reports the hint revealed, per puzzle', async () => {
    render(<PuzzleSequence courseSlug="c" lessonSlug="l" getToken={async () => 'tok'} />);
    await screen.findByText('reveal');
    expect(screen.queryByText('Use the rook')).toBeNull();
    expect(boardProps.at(-1)).toMatchObject({ revealHintsOnRequest: true, showLegalDests: true });

    fireEvent.click(screen.getByText('reveal'));
    expect(screen.getByText('Use the rook')).toBeTruthy();

    // Next puzzle starts hidden again
    fireEvent.click(screen.getByText('2'));
    expect(screen.queryByText('Rook again')).toBeNull();
    expect(screen.queryByText('Use the rook')).toBeNull();
    fireEvent.click(screen.getByText('reveal'));
    expect(screen.getByText('Rook again')).toBeTruthy();
  });
});
