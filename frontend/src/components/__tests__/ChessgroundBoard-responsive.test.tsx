// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import ChessgroundBoard from '../chess/ChessgroundBoard';

const FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// The default (no boardSize) path measures the board's parent container with a
// ResizeObserver. jsdom implements neither ResizeObserver nor real layout, so
// we stub both: a no-op observer plus a mockable clientWidth on the container.
let mockClientWidth = 0;
let clientWidthSpy: ReturnType<typeof Object.getOwnPropertyDescriptor> | undefined;

class MockResizeObserver {
  constructor(_cb: ResizeObserverCallback) {}
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  (globalThis as any).ResizeObserver = MockResizeObserver;
  clientWidthSpy = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get() {
      return mockClientWidth;
    },
  });
});

afterEach(() => {
  delete (globalThis as any).ResizeObserver;
  if (clientWidthSpy) {
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', clientWidthSpy);
  } else {
    delete (HTMLElement.prototype as any).clientWidth;
  }
});

describe('ChessgroundBoard container-based default sizing', () => {
  it('sizes the board to fit its container when no boardSize is passed', () => {
    mockClientWidth = 337;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board).toBeTruthy();
    const width = parseInt(board.style.width, 10);
    // Fills the container exactly, and is wider than the old clipped ~300px.
    expect(width).toBe(337);
    expect(width).toBeGreaterThan(300);
  });

  it('caps at 520px when the container is wider than the max default', () => {
    mockClientWidth = 900;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board.style.width).toBe('520px');
  });

  it('falls back to 520px when the container reports no width', () => {
    mockClientWidth = 0;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board.style.width).toBe('520px');
  });

  it('respects an explicit boardSize prop regardless of the container', () => {
    mockClientWidth = 900;
    const { container } = render(<ChessgroundBoard fen={FEN} boardSize={300} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    expect(board.style.width).toBe('300px');
  });
});
