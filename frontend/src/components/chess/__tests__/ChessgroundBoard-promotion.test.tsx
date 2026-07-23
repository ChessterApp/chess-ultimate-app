// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';

// Capture the config handed to Chessground so the test can drive the board's
// `after` event exactly like a completed user drag would.
let capturedConfig: any = null;
const setSpy = vi.fn();

vi.mock('chessground', () => ({
  Chessground: (_el: HTMLElement, config: any) => {
    capturedConfig = config;
    return {
      set: setSpy,
      setShapes: vi.fn(),
      destroy: vi.fn(),
      redrawAll: vi.fn(),
    };
  },
}));

import ChessgroundBoard from '../ChessgroundBoard';

// White pawn on e7, white to move → e7e8 promotes (e8 kept empty).
const WHITE_PROMO = 'k7/4P3/8/8/8/8/8/7K w - - 0 1';
// Black pawn on d2, black to move → d2d1 promotes (d1 kept empty).
const BLACK_PROMO = 'K7/8/8/8/8/8/3p4/7k b - - 0 1';
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

beforeEach(() => {
  capturedConfig = null;
  setSpy.mockClear();
  (globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

function fireBoardMove(from: string, to: string) {
  act(() => {
    capturedConfig.movable.events.after(from, to);
  });
}

describe('ChessgroundBoard promotion picker', () => {
  it('shows the picker on a white 8th-rank pawn move instead of auto-queening', () => {
    const onMove = vi.fn();
    render(<ChessgroundBoard fen={WHITE_PROMO} onMove={onMove} />);
    fireBoardMove('e7', 'e8');
    expect(screen.getByTestId('promotion-overlay')).toBeTruthy();
    expect(onMove).not.toHaveBeenCalled();
  });

  it('shows the picker on a black 1st-rank pawn move', () => {
    const onMove = vi.fn();
    render(<ChessgroundBoard fen={BLACK_PROMO} orientation="black" onMove={onMove} />);
    fireBoardMove('d2', 'd1');
    expect(screen.getByTestId('promotion-overlay')).toBeTruthy();
    expect(onMove).not.toHaveBeenCalled();
  });

  it('reports the move with the chosen role when knight is picked', () => {
    const onMove = vi.fn();
    render(<ChessgroundBoard fen={WHITE_PROMO} onMove={onMove} />);
    fireBoardMove('e7', 'e8');
    fireEvent.click(screen.getByTestId('promotion-n'));
    expect(onMove).toHaveBeenCalledWith('e7', 'e8', 'n');
    expect(screen.queryByTestId('promotion-overlay')).toBeNull();
  });

  it('cancels and snaps the pawn back when the backdrop is clicked', () => {
    const onMove = vi.fn();
    render(<ChessgroundBoard fen={WHITE_PROMO} onMove={onMove} />);
    fireBoardMove('e7', 'e8');
    setSpy.mockClear();
    fireEvent.click(screen.getByTestId('promotion-overlay'));
    expect(onMove).not.toHaveBeenCalled();
    expect(screen.queryByTestId('promotion-overlay')).toBeNull();
    // Board is reset to the pre-move FEN so the held pawn returns home.
    expect(setSpy).toHaveBeenCalledWith({ fen: WHITE_PROMO });
  });

  it('reports non-promotion moves immediately with no picker', () => {
    const onMove = vi.fn();
    render(<ChessgroundBoard fen={START} onMove={onMove} />);
    fireBoardMove('e2', 'e4');
    expect(onMove).toHaveBeenCalledWith('e2', 'e4');
    expect(screen.queryByTestId('promotion-overlay')).toBeNull();
  });
});
