// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';

let capturedConfig: any = null;
const setAutoShapes = vi.fn();

vi.mock('chessground', () => ({
  Chessground: (_el: HTMLElement, config: any) => {
    capturedConfig = config;
    return { set: vi.fn(), setShapes: vi.fn(), setAutoShapes, destroy: vi.fn(), redrawAll: vi.fn() };
  },
}));

import ChessgroundBoard from '../ChessgroundBoard';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

beforeEach(() => {
  capturedConfig = null;
  setAutoShapes.mockClear();
  (globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
});

describe('ChessgroundBoard hint shapes', () => {
  it('hintSquare draws a green circle; hintMove keeps its arrow; both can coexist', () => {
    const { rerender } = render(<ChessgroundBoard fen={START} hintSquare="e2" />);
    expect(capturedConfig.drawable.autoShapes).toEqual([{ orig: 'e2', brush: 'green' }]);

    rerender(<ChessgroundBoard fen={START} hintMove={['g1', 'f3']} />);
    expect(setAutoShapes).toHaveBeenLastCalledWith([{ orig: 'g1', dest: 'f3', brush: 'green' }]);

    rerender(<ChessgroundBoard fen={START} hintMove={['g1', 'f3']} hintSquare="e2" />);
    expect(setAutoShapes).toHaveBeenLastCalledWith([
      { orig: 'g1', dest: 'f3', brush: 'green' },
      { orig: 'e2', brush: 'green' },
    ]);

    rerender(<ChessgroundBoard fen={START} />);
    expect(setAutoShapes).toHaveBeenLastCalledWith([]);
  });
});
