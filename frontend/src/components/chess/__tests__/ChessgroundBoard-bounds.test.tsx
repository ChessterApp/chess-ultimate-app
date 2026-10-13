// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import React from 'react';

// Chessground memoizes the board's getBoundingClientRect() and only clears it
// on scroll/resize. A board that moves without resizing (layout swap) must
// have that cache dropped before chessground maps the next press to a square.

const cg = vi.hoisted(() => ({
  boardEl: null as HTMLElement | null,
  cached: undefined as DOMRect | undefined,
  clear: vi.fn(),
  boundsAtPress: [] as (DOMRect | undefined)[],
}));

vi.mock('chessground', () => ({
  Chessground: (el: HTMLElement) => {
    const board = document.createElement('cg-board');
    el.appendChild(board);
    cg.boardEl = board;
    const bounds = Object.assign(() => (cg.cached ??= board.getBoundingClientRect()), {
      clear: () => { cg.clear(); cg.cached = undefined; },
    });
    // Chessground's own (bubble-phase) handler, registered on the inner board.
    board.addEventListener('mousedown', () => cg.boundsAtPress.push(cg.cached));
    return {
      state: { dom: { bounds, elements: { board } } },
      set: vi.fn(), setShapes: vi.fn(), setAutoShapes: vi.fn(), selectSquare: vi.fn(), destroy: vi.fn(), redrawAll: vi.fn(),
    };
  },
}));

import ChessgroundBoard from '../ChessgroundBoard';

const FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const rect = (left: number, top: number, size = 400) =>
  ({ left, top, width: size, height: size, right: left + size, bottom: top + size, x: left, y: top }) as DOMRect;

let pos = rect(0, 0);

beforeEach(() => {
  cg.cached = undefined;
  cg.clear.mockClear();
  cg.boundsAtPress.length = 0;
  pos = rect(0, 0);
});
afterEach(() => cleanup());

function mount() {
  render(<ChessgroundBoard fen={FEN} boardSize={400} />);
  cg.boardEl!.getBoundingClientRect = () => pos;
  cg.cached = rect(0, 0); // what chessground measured at creation
}

describe('ChessgroundBoard stale bounds', () => {
  it('clears cached bounds before a press when the board moved without resizing', () => {
    mount();
    pos = rect(118, -36);
    cg.boardEl!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    expect(cg.clear).toHaveBeenCalled();
    expect(cg.boundsAtPress).toEqual([undefined]); // chessground re-measures on this press
  });

  it('keeps the cache when the board has not moved', () => {
    mount();
    cg.boardEl!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    expect(cg.clear).not.toHaveBeenCalled();
    expect(cg.boundsAtPress).toEqual([rect(0, 0)]);
  });

  it('also checks on touchstart and pointerdown', () => {
    mount();
    pos = rect(10, 0);
    cg.boardEl!.dispatchEvent(new Event('touchstart', { bubbles: true }));
    expect(cg.clear).toHaveBeenCalledTimes(1);
    cg.cached = rect(0, 0);
    cg.boardEl!.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(cg.clear).toHaveBeenCalledTimes(2);
  });
});
