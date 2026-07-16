/**
 * @vitest-environment jsdom
 *
 * BoardEditor is migrated from the legacy chessboard library to the shared
 * ChessgroundBoard wrapper (phase 5b) in free-placement editor mode. These
 * tests stub ChessgroundBoard to capture the props it receives and to drive its
 * onChange / onSelect callbacks, verifying the editor renders an editable board,
 * tracks the FEN it exposes, and preserves piece placement, removal, and
 * board-drag sync.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { render, cleanup, fireEvent, act, screen } from '@testing-library/react';

// Capture every props object ChessgroundBoard is rendered with.
const boardProps = vi.hoisted(() => [] as any[]);

vi.mock('@/components/chess/ChessgroundBoard', () => ({
  default: (props: any) => {
    boardProps.push(props);
    return <div data-testid="cg-board" data-fen={props.fen} data-editable={String(props.editable)} />;
  },
}));

// EditorControls is unrelated to the board migration — stub it out.
vi.mock('../EditorControls', () => ({ default: () => <div data-testid="editor-controls" /> }));

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string) => k,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => ({ get: () => null }),
}));

import BoardEditor from '../BoardEditor';
import { STARTING_FEN, EMPTY_FEN } from '@/lib/chess/fenEditor';

function lastBoardProps() {
  return boardProps[boardProps.length - 1];
}

describe('BoardEditor → ChessgroundBoard migration', () => {
  beforeEach(() => {
    boardProps.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  it('renders an editable board at the starting position by default', () => {
    render(<BoardEditor />);
    const props = lastBoardProps();
    expect(props.editable).toBe(true);
    expect(props.fen).toBe(STARTING_FEN);
    expect(typeof props.onChange).toBe('function');
    expect(typeof props.onSelect).toBe('function');
  });

  it('respects an explicit initial FEN', () => {
    render(<BoardEditor initialFen={EMPTY_FEN} />);
    expect(lastBoardProps().fen).toBe(EMPTY_FEN);
  });

  it('syncs the FEN when the board reports a drag/drop change', () => {
    render(<BoardEditor initialFen={EMPTY_FEN} />);

    // Chessground reports the new placement FEN (board part only).
    act(() => lastBoardProps().onChange('8/8/8/8/4P3/8/8/8'));

    expect(lastBoardProps().fen).toBe('8/8/8/8/4P3/8/8/8 w - - 0 1');
  });

  it('places a selected spare piece when a square is clicked', () => {
    render(<BoardEditor initialFen={EMPTY_FEN} />);

    // Select the white queen from the spare-piece palette.
    fireEvent.click(screen.getByAltText('wQ'));
    // Click e4 on the board.
    act(() => lastBoardProps().onSelect('e4'));

    expect(lastBoardProps().fen).toBe('8/8/8/8/4Q3/8/8/8 w - - 0 1');
  });

  it('removes a piece with the trash tool', () => {
    render(<BoardEditor initialFen="8/8/8/8/4P3/8/8/8 w - - 0 1" />);

    // Select the trash tool (rendered in both spare-piece rows), then click the
    // occupied square.
    fireEvent.click(screen.getAllByTitle('deleteTool')[0]);
    act(() => lastBoardProps().onSelect('e4'));

    expect(lastBoardProps().fen).toBe(EMPTY_FEN);
  });
});
