// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';
import React from 'react';
import TugBoard, { pointToSquare } from '../TugBoard';
import type { TugPuzzle } from '@/lib/tug-of-war/types';

// Minimal chessground stand-in: implements the tap-piece → tap-square flow of
// selectSquare (select a movable piece, then a dest fires movable.events.after)
// so the board's real move handling runs end to end.
type FakeConfig = {
  movable?: { dests?: Map<string, string[]>; events?: { after?: (o: string, d: string) => void } };
};
const grounds = vi.hoisted(() => [] as Array<{ el: HTMLElement; selectSquare: (k: string) => void }>);
vi.mock('chessground', () => ({
  Chessground: (el: HTMLElement, config: FakeConfig) => {
    let dests = config.movable?.dests ?? new Map<string, string[]>();
    const after = config.movable?.events?.after;
    let selected: string | undefined;
    const api = {
      el,
      set: (c: FakeConfig) => {
        if (c.movable?.dests) dests = c.movable.dests;
      },
      selectSquare: vi.fn((key: string) => {
        if (selected && dests.get(selected)?.includes(key)) {
          const orig = selected;
          selected = undefined;
          after?.(orig, key);
          return;
        }
        selected = dests.has(key) ? key : undefined;
      }),
      redrawAll: () => {},
      destroy: () => {},
    };
    grounds.push(api);
    return api;
  },
}));

// Mate-in-1 for white: Ra1–a8#.
const PUZZLE: TugPuzzle = {
  id: 'test-1',
  fen: '6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1',
  moves: ['a1a8'],
  rating: 800,
  themes: ['mateIn1'],
};
// Mirror for black (board flipped): Ra8–a1#.
const PUZZLE_BLACK: TugPuzzle = {
  id: 'test-2',
  fen: 'r3k3/8/8/8/8/8/5PPP/6K1 b - - 0 1',
  moves: ['a8a1'],
  rating: 800,
  themes: ['mateIn1'],
};

const noop = () => {};
const RECT = { left: 0, top: 0, width: 400, height: 400 };

describe('pointToSquare', () => {
  it('maps corners for white', () => {
    expect(pointToSquare(1, 399, RECT, 'white')).toBe('a1');
    expect(pointToSquare(399, 399, RECT, 'white')).toBe('h1');
    expect(pointToSquare(1, 1, RECT, 'white')).toBe('a8');
    expect(pointToSquare(399, 1, RECT, 'white')).toBe('h8');
  });

  it('maps corners for black', () => {
    expect(pointToSquare(1, 399, RECT, 'black')).toBe('h8');
    expect(pointToSquare(399, 399, RECT, 'black')).toBe('a8');
    expect(pointToSquare(1, 1, RECT, 'black')).toBe('h1');
    expect(pointToSquare(399, 1, RECT, 'black')).toBe('a1');
  });

  it('honours the rect offset', () => {
    const rect = { left: 500, top: 100, width: 400, height: 400 };
    expect(pointToSquare(525, 475, rect, 'white')).toBe('a1');
    expect(pointToSquare(275, 475, rect, 'white')).toBeNull();
  });

  it('returns null out of bounds', () => {
    expect(pointToSquare(-1, 10, RECT, 'white')).toBeNull();
    expect(pointToSquare(10, -1, RECT, 'white')).toBeNull();
    expect(pointToSquare(400, 10, RECT, 'white')).toBeNull();
    expect(pointToSquare(10, 400, RECT, 'black')).toBeNull();
  });
});

describe('TugBoard', () => {
  const realRect = HTMLElement.prototype.getBoundingClientRect;

  beforeEach(() => {
    grounds.length = 0;
    // Board A sits at x 0–400, board B at x 500–900; both 400px tall.
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      const left = this.closest('#board-b') ? 500 : 0;
      return { left, top: 0, width: 400, height: 400, right: left + 400, bottom: 400, x: left, y: 0 } as DOMRect;
    };
  });

  afterEach(() => {
    cleanup();
    HTMLElement.prototype.getBoundingClientRect = realRect;
    window.history.replaceState({}, '', '/');
  });

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

  const renderTwo = async () => {
    const solvedA = vi.fn();
    const solvedB = vi.fn();
    const { container } = render(
      <>
        <div id="board-a">
          <TugBoard puzzle={PUZZLE} accent="blue" onSolved={solvedA} onWrong={noop} />
        </div>
        <div id="board-b">
          <TugBoard puzzle={PUZZLE_BLACK} accent="orange" onSolved={solvedB} onWrong={noop} />
        </div>
      </>,
    );
    await waitFor(() => expect(grounds).toHaveLength(2));
    const boardA = container.querySelector('#board-a .chessground-board') as HTMLElement;
    const boardB = container.querySelector('#board-b .chessground-board') as HTMLElement;
    const groundA = grounds.find((g) => g.el === boardA)!;
    const groundB = grounds.find((g) => g.el === boardB)!;
    return { boardA, boardB, groundA, groundB, solvedA, solvedB };
  };

  const touch = (pointerId: number, clientX: number, clientY: number, pointerType = 'touch') => ({
    pointerId,
    pointerType,
    clientX,
    clientY,
    bubbles: true,
  });

  it('takes interleaved touches on two boards independently', async () => {
    const { boardA, boardB, groundA, groundB, solvedA, solvedB } = await renderTwo();

    // A: finger 1 on a1. B (black, flipped): finger 2 on a8 = bottom-right.
    fireEvent.pointerDown(boardA, touch(1, 25, 375));
    fireEvent.pointerDown(boardB, touch(2, 875, 375));
    fireEvent.pointerUp(boardB, touch(2, 875, 375));
    fireEvent.pointerUp(boardA, touch(1, 25, 375));
    expect(groundA.selectSquare).toHaveBeenCalledWith('a1');
    expect(groundB.selectSquare).toHaveBeenCalledWith('a8');
    expect(groundA.selectSquare).toHaveBeenCalledTimes(1);
    expect(groundB.selectSquare).toHaveBeenCalledTimes(1);

    // Destinations, again overlapping: A → a8 (top-left), B → a1 (top-right).
    fireEvent.pointerDown(boardA, touch(3, 25, 25));
    fireEvent.pointerDown(boardB, touch(4, 875, 25));
    fireEvent.pointerUp(boardA, touch(3, 25, 25));
    expect(solvedA).toHaveBeenCalledTimes(1);
    expect(solvedB).not.toHaveBeenCalled();
    fireEvent.pointerUp(boardB, touch(4, 875, 25));
    expect(groundA.selectSquare).toHaveBeenLastCalledWith('a8');
    expect(groundB.selectSquare).toHaveBeenLastCalledWith('a1');
    expect(solvedB).toHaveBeenCalledTimes(1);
  });

  it('treats a finger slid piece → square as a move', async () => {
    const { boardA, groundA, solvedA } = await renderTwo();
    fireEvent.pointerDown(boardA, touch(1, 25, 375));
    fireEvent.pointerUp(boardA, touch(1, 25, 25));
    expect(groundA.selectSquare.mock.calls).toEqual([['a1'], ['a8']]);
    expect(solvedA).toHaveBeenCalledTimes(1);
  });

  it('ignores cancelled touches', async () => {
    const { boardA, groundA } = await renderTwo();
    fireEvent.pointerDown(boardA, touch(1, 25, 375));
    fireEvent.pointerCancel(boardA, touch(1, 25, 375));
    fireEvent.pointerUp(boardA, touch(1, 25, 375));
    expect(groundA.selectSquare).not.toHaveBeenCalled();
  });

  it('leaves mouse pointers to chessground', async () => {
    const { boardA, groundA } = await renderTwo();
    fireEvent.pointerDown(boardA, touch(1, 25, 375, 'mouse'));
    fireEvent.pointerUp(boardA, touch(1, 25, 375, 'mouse'));
    expect(groundA.selectSquare).not.toHaveBeenCalled();
  });

  it('keeps touchstart from reaching chessground but lets mousedown through', async () => {
    const { boardA } = await renderTwo();
    const onTouch = vi.fn();
    const onMouse = vi.fn();
    boardA.addEventListener('touchstart', onTouch);
    boardA.addEventListener('mousedown', onMouse);
    fireEvent.touchStart(boardA);
    fireEvent.mouseDown(boardA);
    expect(onTouch).not.toHaveBeenCalled();
    expect(onMouse).toHaveBeenCalledTimes(1);
  });

  it('renders the touch debug panel only with ?touchdebug=1', async () => {
    const first = render(<TugBoard puzzle={PUZZLE} accent="blue" onSolved={noop} onWrong={noop} />);
    expect(first.queryByTestId('tug-touchdebug')).toBeNull();
    first.unmount();

    window.history.replaceState({}, '', '/?touchdebug=1');
    const { container, findByTestId } = render(
      <TugBoard puzzle={PUZZLE} accent="blue" onSolved={noop} onWrong={noop} />,
    );
    const panel = await findByTestId('tug-touchdebug');
    expect(panel.textContent).toMatch(/maxTouchPoints/);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    fireEvent.pointerDown(board, touch(7, 25, 375, 'pen'));
    await waitFor(() => expect(panel.textContent).toMatch(/active 1 · last pen/));
  });
});
