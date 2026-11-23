// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

let capturedConfig: any = null;
let latestAfter: ((orig: string, dest: string) => void) | null = null;
const setCalls: any[] = [];

vi.mock('chessground', () => ({
  Chessground: (_el: HTMLElement, config: any) => {
    capturedConfig = config;
    return {
      set: (cfg: any) => {
        setCalls.push(cfg);
        if (cfg?.movable?.events?.after) latestAfter = cfg.movable.events.after;
      },
      destroy: vi.fn(),
    };
  },
}));
vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('@/hooks/useHaptic', () => ({ useHaptic: () => ({ onPuzzleCorrect: vi.fn(), onPuzzleWrong: vi.fn() }) }));
vi.mock('@/hooks/useSoundEffects', () => ({ useSoundEffects: () => ({ play: vi.fn() }) }));
vi.mock('../LottieCelebration', () => ({ default: () => null }));
vi.mock('../ArrowOverlay', () => ({
  default: ({ visible }: { visible: boolean }) => <div data-testid="arrow" data-visible={String(visible)} />,
}));

import AnimatedChessBoard from '../AnimatedChessBoard';

const FEN = '4k3/8/8/8/8/8/8/R3K3 w - - 0 1';
const FEN2 = '4k3/8/8/8/8/8/8/1R2K3 w - - 0 1';

const arrowVisible = () => screen.getByTestId('arrow').getAttribute('data-visible');

function renderBoard(props: Partial<React.ComponentProps<typeof AnimatedChessBoard>> = {}) {
  return render(
    <AnimatedChessBoard
      fen={FEN}
      solutionMove="a1a8"
      arrowFromSquare="a1"
      strictValidation
      enableAnimations={false}
      onCorrectMove={vi.fn()}
      {...props}
    />
  );
}

beforeEach(() => {
  capturedConfig = null;
  latestAfter = null;
  setCalls.length = 0;
  vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({ width: 400, height: 400 } as DOMRect);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('AnimatedChessBoard revealHintsOnRequest', () => {
  it('without the prop the arrow shows from the start and hints count as revealed', async () => {
    const onBoardStateChange = vi.fn();
    renderBoard({ onBoardStateChange });
    expect(arrowVisible()).toBe('true');
    expect(onBoardStateChange).toHaveBeenLastCalledWith(expect.objectContaining({ hintRevealed: true }));
  });

  it('hides the arrow until Hint is pressed', async () => {
    const onBoardStateChange = vi.fn();
    renderBoard({ revealHintsOnRequest: true, onBoardStateChange });
    expect(arrowVisible()).toBe('false');
    expect(onBoardStateChange).toHaveBeenLastCalledWith(expect.objectContaining({ hintRevealed: false }));

    fireEvent.click(screen.getByLabelText('lesson.showHint'));
    expect(arrowVisible()).toBe('true');
    expect(onBoardStateChange).toHaveBeenLastCalledWith(expect.objectContaining({ hintRevealed: true }));
  });

  it('reveals the arrow after a wrong move', async () => {
    const onBoardStateChange = vi.fn();
    renderBoard({ revealHintsOnRequest: true, onBoardStateChange });
    await waitFor(() => expect(latestAfter).not.toBeNull());

    await act(async () => {
      latestAfter!('a1', 'a2');
    });
    await waitFor(() => expect(arrowVisible()).toBe('true'));
    expect(onBoardStateChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ attempts: 1, hintRevealed: true })
    );
  });

  it('hides the arrow again when the puzzle changes', async () => {
    const { rerender } = renderBoard({ revealHintsOnRequest: true });
    fireEvent.click(screen.getByLabelText('lesson.showHint'));
    expect(arrowVisible()).toBe('true');

    rerender(
      <AnimatedChessBoard
        fen={FEN2}
        solutionMove="b1b8"
        arrowFromSquare="b1"
        strictValidation
        enableAnimations={false}
        onCorrectMove={vi.fn()}
        revealHintsOnRequest
      />
    );
    expect(arrowVisible()).toBe('false');
  });

  it('hides the arrow again on Reset', async () => {
    renderBoard({ revealHintsOnRequest: true });
    fireEvent.click(screen.getByLabelText('lesson.showHint'));
    expect(arrowVisible()).toBe('true');
    fireEvent.click(screen.getByLabelText('lesson.reset'));
    expect(arrowVisible()).toBe('false');
  });

  it('a hinted student can still solve the puzzle', async () => {
    const onBoardStateChange = vi.fn();
    renderBoard({ revealHintsOnRequest: true, onBoardStateChange });
    await waitFor(() => expect(latestAfter).not.toBeNull());
    fireEvent.click(screen.getByLabelText('lesson.showHint'));
    await act(async () => {
      latestAfter!('a1', 'a8');
    });
    expect(onBoardStateChange).toHaveBeenLastCalledWith(expect.objectContaining({ solved: true, hintRevealed: true }));
  });
});

describe('AnimatedChessBoard showLegalDests', () => {
  it('passes legal dests to chessground and refreshes them after a move', async () => {
    renderBoard({ showLegalDests: true });
    await waitFor(() => expect(capturedConfig).not.toBeNull());
    expect(capturedConfig.movable.showDests).toBe(true);
    expect(capturedConfig.movable.dests.get('a1')).toContain('a8');

    await waitFor(() => expect(latestAfter).not.toBeNull());
    setCalls.length = 0;
    await act(async () => {
      latestAfter!('a1', 'a2');
    });
    await waitFor(() =>
      expect(setCalls.some((c) => c.movable?.showDests === true && c.movable.dests?.get('a1'))).toBe(true)
    );
  });

  it('keeps the dots off by default', async () => {
    renderBoard();
    await waitFor(() => expect(capturedConfig).not.toBeNull());
    expect(capturedConfig.movable.showDests).toBe(false);
    expect(capturedConfig.movable.dests).toBeUndefined();
  });
});
