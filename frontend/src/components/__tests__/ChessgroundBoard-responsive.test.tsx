// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import ChessgroundBoard from '../chess/ChessgroundBoard';

const FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

function setWidth(w: number) {
  Object.defineProperty(window, 'innerWidth', { value: w, writable: true, configurable: true });
}

describe('ChessgroundBoard responsive default sizing', () => {
  beforeEach(() => {
    setWidth(1024);
  });

  it('shrinks to fit a 375px viewport when no boardSize is passed', () => {
    setWidth(375);
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board).toBeTruthy();
    const width = parseInt(board.style.width, 10);
    // Must be smaller than the old fixed 520px and fit within the viewport.
    expect(width).toBeLessThan(520);
    expect(width).toBeLessThanOrEqual(375);
    expect(width).toBeGreaterThan(0);
  });

  it('defaults to 520px on desktop when no boardSize is passed', () => {
    setWidth(1440);
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board.style.width).toBe('520px');
  });

  it('respects an explicit boardSize prop regardless of viewport', () => {
    setWidth(375);
    const { container } = render(<ChessgroundBoard fen={FEN} boardSize={300} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board.style.width).toBe('300px');
  });
});
