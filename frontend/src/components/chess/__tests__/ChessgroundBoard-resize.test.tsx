// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import React from 'react';

// Chessground lays pieces out in absolute px for the size it was created at.
// These tests pin that we (a) only create it at the measured size and (b)
// re-place the pieces ourselves whenever the size may have changed, without
// waiting on a ResizeObserver notification (late/missing on iPad Safari).

const created: number[] = [];
const redrawAll = vi.fn();
const destroy = vi.fn();

vi.mock('chessground', () => ({
  Chessground: (el: HTMLElement) => {
    created.push(parseInt(el.style.width, 10));
    return { set: vi.fn(), setShapes: vi.fn(), setAutoShapes: vi.fn(), selectSquare: vi.fn(), destroy, redrawAll };
  },
}));

import ChessgroundBoard from '../ChessgroundBoard';

const FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

let mockClientWidth = 0;
let clientWidthDesc: PropertyDescriptor | undefined;
let visibility: DocumentVisibilityState = 'visible';
const observerCallbacks: ResizeObserverCallback[] = [];
const frames = new Map<number, FrameRequestCallback>();
let frameId = 0;

/** Dispatch inside act(), then run the queued animation frames. */
function fire(fn: () => void) {
  act(() => {
    fn();
    const due = [...frames.values()];
    frames.clear();
    due.forEach((cb) => cb(0));
  });
}

class MockResizeObserver {
  constructor(cb: ResizeObserverCallback) {
    observerCallbacks.push(cb);
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  created.length = 0;
  observerCallbacks.length = 0;
  redrawAll.mockClear();
  destroy.mockClear();
  visibility = 'visible';
  (globalThis as any).ResizeObserver = MockResizeObserver;
  // Queue frames and flush them explicitly so the per-frame throttle is observable.
  frames.clear();
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    frames.set(++frameId, cb);
    return frameId;
  });
  vi.stubGlobal('cancelAnimationFrame', (id: number) => frames.delete(id));
  clientWidthDesc = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'clientWidth');
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
    configurable: true,
    get: () => mockClientWidth,
  });
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (globalThis as any).ResizeObserver;
  if (clientWidthDesc) Object.defineProperty(HTMLElement.prototype, 'clientWidth', clientWidthDesc);
  else delete (HTMLElement.prototype as any).clientWidth;
  delete (document as any).visibilityState;
});

function boardWidth(container: HTMLElement) {
  return (container.querySelector('.chessground-board') as HTMLElement).style.width;
}

describe('ChessgroundBoard resize handling', () => {
  it('creates chessground at the measured container size, never at 520 first', () => {
    mockClientWidth = 355;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    expect(created).toEqual([355]);
    expect(boardWidth(container)).toBe('355px');
  });

  it('redraws when the container size changes, with no ResizeObserver callback fired', () => {
    mockClientWidth = 520;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    redrawAll.mockClear();

    mockClientWidth = 355;
    fire(() => window.dispatchEvent(new Event('resize')));

    expect(boardWidth(container)).toBe('355px');
    expect(redrawAll).toHaveBeenCalled();
    expect(created).toEqual([520]); // updated in place, not re-created
  });

  it('visibilitychange → visible re-measures and redraws; hidden does not', () => {
    mockClientWidth = 520;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    redrawAll.mockClear();

    mockClientWidth = 400;
    visibility = 'hidden';
    fire(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(redrawAll).not.toHaveBeenCalled();
    expect(boardWidth(container)).toBe('520px');

    visibility = 'visible';
    fire(() => document.dispatchEvent(new Event('visibilitychange')));
    expect(boardWidth(container)).toBe('400px');
    expect(redrawAll).toHaveBeenCalled();
  });

  it('pageshow (bfcache restore) and orientationchange redraw even at an unchanged size', () => {
    mockClientWidth = 400;
    render(<ChessgroundBoard fen={FEN} viewOnly />);
    redrawAll.mockClear();

    const ev = new Event('pageshow') as PageTransitionEvent;
    Object.defineProperty(ev, 'persisted', { value: true });
    fire(() => window.dispatchEvent(ev));
    expect(redrawAll).toHaveBeenCalledTimes(1);

    fire(() => window.dispatchEvent(new Event('orientationchange')));
    expect(redrawAll).toHaveBeenCalledTimes(2);
  });

  it('throttles bursts of events to one redraw per frame', () => {
    mockClientWidth = 400;
    render(<ChessgroundBoard fen={FEN} viewOnly />);
    redrawAll.mockClear();
    fire(() => {
      for (let i = 0; i < 5; i++) window.dispatchEvent(new Event('orientationchange'));
    });
    expect(redrawAll).toHaveBeenCalledTimes(1);
  });

  it('body ResizeObserver only redraws when the board rect actually changed', () => {
    mockClientWidth = 400;
    const { container } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const board = container.querySelector('.chessground-board') as HTMLElement;
    let top = 0;
    board.getBoundingClientRect = () => ({ left: 0, top, width: 400, height: 400 }) as DOMRect;
    redrawAll.mockClear();
    const fireAll = () => fire(() => observerCallbacks.forEach((cb) => cb([], {} as ResizeObserver)));

    fireAll(); // first observation records the rect
    redrawAll.mockClear();
    fireAll();
    expect(redrawAll).not.toHaveBeenCalled();

    top = 40; // layout shift above the board
    fireAll();
    expect(redrawAll).toHaveBeenCalledTimes(1);
  });

  it('removes its window/document listeners on unmount', () => {
    mockClientWidth = 400;
    const addWin = vi.spyOn(window, 'addEventListener');
    const remWin = vi.spyOn(window, 'removeEventListener');
    const addDoc = vi.spyOn(document, 'addEventListener');
    const remDoc = vi.spyOn(document, 'removeEventListener');
    const { unmount } = render(<ChessgroundBoard fen={FEN} viewOnly />);
    const names = ['pageshow', 'orientationchange', 'resize'];
    const added = addWin.mock.calls.filter(([n]) => names.includes(n as string));
    expect(added.map(([n]) => n).sort()).toEqual([...names].sort());
    unmount();
    for (const [name, fn] of added) {
      expect(remWin).toHaveBeenCalledWith(name, fn);
    }
    const vis = addDoc.mock.calls.find(([n]) => n === 'visibilitychange')!;
    expect(remDoc).toHaveBeenCalledWith('visibilitychange', vis[1]);
    expect(destroy).toHaveBeenCalledTimes(1);

    redrawAll.mockClear();
    fire(() => {
      window.dispatchEvent(new Event('resize'));
      document.dispatchEvent(new Event('visibilitychange'));
    });
    expect(redrawAll).not.toHaveBeenCalled();
    expect(frames.size).toBe(0);
  });

  it('explicit boardSize: created immediately at that size, ignores the container', () => {
    mockClientWidth = 900;
    const { container, rerender } = render(<ChessgroundBoard fen={FEN} boardSize={300} viewOnly />);
    expect(created).toEqual([300]);
    expect(boardWidth(container)).toBe('300px');
    expect(redrawAll).not.toHaveBeenCalled();

    mockClientWidth = 200;
    fire(() => window.dispatchEvent(new Event('resize')));
    expect(boardWidth(container)).toBe('300px');

    // A caller-driven size change is redrawn in place too.
    rerender(<ChessgroundBoard fen={FEN} boardSize={360} viewOnly />);
    expect(boardWidth(container)).toBe('360px');
    expect(created).toEqual([300]);
    expect(redrawAll).toHaveBeenCalled();
  });
});
