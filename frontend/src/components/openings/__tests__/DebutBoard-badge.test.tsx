// @vitest-environment jsdom
//
// Move-quality badge pinned to the destination square's top-right corner.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';

vi.mock('@/components/chess/ChessgroundBoard', () => ({ default: () => <div data-testid="cg" /> }));

import DebutBoard from '../DebutBoard';

afterEach(() => cleanup());

const noop = () => {};
function renderBoard(props: Partial<React.ComponentProps<typeof DebutBoard>>) {
  return render(
    <DebutBoard
      fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1"
      orientation="white"
      onMove={noop} onReset={noop} onGoToStart={noop} onPrev={noop} onNext={noop} onGoToEnd={noop} onFlip={noop}
      {...props}
    />,
  );
}

describe('DebutBoard square badge', () => {
  it('renders the symbol over the destination square', () => {
    renderBoard({ squareBadge: { square: 'e4', symbol: '!!', color: '#26c2a3' } });
    const badge = screen.getByTestId('square-badge');
    expect(badge.textContent).toBe('!!');
    // 1024px window → 520px board, 65px squares; e4 is column 4, row 4 from the top.
    const size = Math.round(65 * 0.42);
    expect(getComputedStyle(badge).left).toBe(`${5 * 65 - size * 0.7}px`);
    expect(getComputedStyle(badge).top).toBe(`${4 * 65 - size * 0.3}px`);
  });

  it('mirrors the position for Black', () => {
    renderBoard({ orientation: 'black', squareBadge: { square: 'h1', symbol: '?', color: '#f08c00' } });
    const badge = screen.getByTestId('square-badge');
    expect(getComputedStyle(badge).left).toBe(`${65 - Math.round(65 * 0.42) * 0.7}px`);
  });

  it('renders nothing without a badge', () => {
    renderBoard({});
    expect(screen.queryByTestId('square-badge')).toBeNull();
  });
});
