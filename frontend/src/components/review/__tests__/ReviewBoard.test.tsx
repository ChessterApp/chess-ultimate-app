/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup } from '@testing-library/react';
import { renderIntl } from './intl';

// Chessground needs a real board runtime; stub it. The stub reports a fixed
// measured size via onSizeChange so the box-sizing wiring can be tested.
vi.mock('@/components/chess/ChessgroundBoard', () => ({
  default: ({
    onSizeChange,
    arrows = [],
    highlightSquares = [],
  }: {
    onSizeChange?: (px: number) => void;
    arrows?: Array<{ from: string; to: string; brush: string }>;
    highlightSquares?: string[];
  }) => {
    React.useEffect(() => {
      onSizeChange?.(320);
    }, [onSizeChange]);
    return (
      <div
        data-testid="cg-stub"
        data-arrows={arrows.map((a) => `${a.from}${a.to}:${a.brush}`).join(',')}
        data-highlights={highlightSquares.join(',')}
      />
    );
  },
}));

import ReviewBoard, { squareToColRow, squareTintStyle, badgeTuckStyle } from '../ReviewBoard';
import { REVIEW_FIXTURE } from './fixture';

afterEach(cleanup);

describe('squareToColRow', () => {
  it('maps squares for white orientation (a-file left, rank 8 top)', () => {
    expect(squareToColRow('a8', 'white')).toEqual({ col: 0, row: 0 });
    expect(squareToColRow('h1', 'white')).toEqual({ col: 7, row: 7 });
    expect(squareToColRow('d3', 'white')).toEqual({ col: 3, row: 5 });
    expect(squareToColRow('h7', 'white')).toEqual({ col: 7, row: 1 });
  });

  it('flips both axes for black orientation', () => {
    expect(squareToColRow('a8', 'black')).toEqual({ col: 7, row: 7 });
    expect(squareToColRow('h1', 'black')).toEqual({ col: 0, row: 0 });
    expect(squareToColRow('d3', 'black')).toEqual({ col: 4, row: 2 });
  });
});

describe('squareTintStyle', () => {
  it('produces a full-square box at the right board %', () => {
    expect(squareTintStyle('d3', 'white')).toEqual({
      left: '37.5%',
      top: '62.5%',
      width: '12.5%',
      height: '12.5%',
    });
  });
});

describe('badgeTuckStyle', () => {
  it('tucks the badge over the destination top-right corner', () => {
    // h7 white → corner at (100%, 12.5%), pulled back by half a 5.5% badge.
    expect(badgeTuckStyle('h7', 'white', 5.5)).toEqual({
      left: '97.25%',
      top: '9.75%',
      width: '5.5%',
      height: '5.5%',
    });
  });
});

describe('ReviewBoard overlays', () => {
  const brilliant = REVIEW_FIXTURE.moves[5]; // Bxh7+, uci d3h7

  it('tints the from + to squares of the current move', () => {
    const { getAllByTestId } = renderIntl(
      <ReviewBoard fen="x" orientation="white" move={brilliant} />,
    );
    const tints = getAllByTestId('square-tint');
    expect(tints.map((t) => t.getAttribute('data-square')).sort()).toEqual(['d3', 'h7']);
    // Tint colour reads from the classification var.
    expect(tints[0].getAttribute('style')).toContain('--color-classification-brilliant');
  });

  it('places the badge on the destination square (both orientations)', () => {
    const white = renderIntl(<ReviewBoard fen="x" orientation="white" move={brilliant} />);
    const wBadge = white.getByTestId('board-badge');
    expect(wBadge.getAttribute('data-square')).toBe('h7');
    expect(wBadge.getAttribute('style')).toContain('97.25%'); // white tuck left
    cleanup();

    const black = renderIntl(<ReviewBoard fen="x" orientation="black" move={brilliant} />);
    const bBadge = black.getByTestId('board-badge');
    expect(bBadge.getAttribute('data-square')).toBe('h7');
    // h7 black → col 0, row 6 → corner left (1*12.5)=12.5 → 12.5-2.75 = 9.75%
    expect(bBadge.getAttribute('style')).toContain('left: 9.75%');
  });

  it('renders no overlays without a move', () => {
    const { queryByTestId, queryAllByTestId } = renderIntl(
      <ReviewBoard fen="x" orientation="white" move={null} />,
    );
    expect(queryAllByTestId('square-tint')).toHaveLength(0);
    expect(queryByTestId('board-badge')).toBeNull();
  });
});

describe('ReviewBoard sizing', () => {
  it('forwards the measured board size and drives the box height from it', () => {
    const onBoardSize = vi.fn();
    const { getByTestId } = renderIntl(
      <ReviewBoard fen="x" orientation="white" move={null} onBoardSize={onBoardSize} />,
    );
    // The measured px is surfaced to the caller (for the eval-bar height)...
    expect(onBoardSize).toHaveBeenCalledWith(320);
    // ...and drives the box height so the box is exactly square (no Safari
    // aspect-ratio height derivation, which caused dead space below the board).
    const box = getByTestId('review-board');
    expect(box.style.height).toBe('320px');
    expect(box.style.aspectRatio).toBe('');
  });
});

describe('ReviewBoard coach arrows (Explain marks, 2026-10-21)', () => {
  const move = { uci: 'e2e4', classification: 'mistake' as const, best: { uci: 'd2d4' } };

  it('draws the best-move arrow when the coach drew none', () => {
    const { getByTestId } = renderIntl(<ReviewBoard fen={REVIEW_FIXTURE.moves[0].fen} move={move} />);
    expect(getByTestId('cg-stub').getAttribute('data-arrows')).toBe('d2d4:blue');
  });

  it("draws the coach's arrows and highlights instead", () => {
    const { getByTestId } = renderIntl(
      <ReviewBoard
        fen={REVIEW_FIXTURE.moves[0].fen}
        move={move}
        coachArrows={[
          { from: 'c6', to: 'd4', brush: 'green' },
          { from: 'd4', to: 'e2', brush: 'red' },
        ]}
        coachSquares={['b3']}
      />,
    );
    const stub = getByTestId('cg-stub');
    expect(stub.getAttribute('data-arrows')).toBe('c6d4:green,d4e2:red');
    expect(stub.getAttribute('data-highlights')).toBe('b3');
  });
});
