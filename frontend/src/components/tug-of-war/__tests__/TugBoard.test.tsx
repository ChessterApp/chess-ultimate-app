// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import TugBoard from '../TugBoard';
import type { TugPuzzle } from '@/lib/tug-of-war/types';

// Mate-in-1: white rook to a1... any legal puzzle works; we only assert markup.
const PUZZLE: TugPuzzle = {
  id: 'test-1',
  fen: '6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1',
  moves: ['a1a8'],
  rating: 800,
  themes: ['mateIn1'],
};

const noop = () => {};

describe('TugBoard coordinate theme', () => {
  // Regression guard: the mounted board div must carry the `chessground-board`
  // class. That class is what makes the shared theme's size-relative coordinate
  // rules (.chessground-board.cg-wrap coords.files/.ranks) apply. Without it the
  // board fell back to chessground base.css fixed-pixel offsets, drifting every
  // file right (h off-board) and every rank up (8 clipped). Matches how the
  // /database board (ChessgroundBoard) is themed.
  it('mounts the board on a .chessground-board element', () => {
    const { container } = render(
      <TugBoard puzzle={PUZZLE} accent="blue" onSolved={noop} onWrong={noop} />,
    );
    const board = container.querySelector('.chessground-board');
    expect(board).toBeTruthy();
  });
});
