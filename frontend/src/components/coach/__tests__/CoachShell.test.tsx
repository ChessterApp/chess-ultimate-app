/**
 * @vitest-environment jsdom
 */
import React, { useReducer } from 'react';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';
import CoachShell from '../CoachShell';
import { sheetReducer, MOVE_STRIP_PX, PEEK_MIN_PX, PLAY_COMPOSER_PX, PLAY_PEEK_PX } from '@/lib/coach/sheet-detent';

const coach = en.coach;

function Harness({ peekPx }: { peekPx?: number }) {
  const [detent, dispatch] = useReducer(sheetReducer, 'peek');
  return (
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <CoachShell
        bar={<header>bar</header>}
        above={peekPx === undefined ? undefined : <div data-testid="coach-row" />}
        board={<div data-testid="board" />}
        below={<div data-testid="strip" />}
        stageChrome={MOVE_STRIP_PX}
        peekPx={peekPx}
        detent={detent}
        onSheet={dispatch}
        sheet={<textarea aria-label="composer" onFocus={() => dispatch({ type: 'composer_focus' })} />}
        keyboard={{ open: false, top: 0, height: 0 }}
      />
    </NextIntlClientProvider>
  );
}

const detent = () => screen.getByTestId('coach-shell').dataset.detent;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** A ResizeObserver whose callbacks the test fires, after setting the content's height. */
function mockResizeObserver() {
  const callbacks: Array<() => void> = [];
  vi.stubGlobal(
    'ResizeObserver',
    class {
      constructor(cb: () => void) {
        callbacks.push(cb);
      }
      observe() {}
      disconnect() {}
    },
  );
  return (contentPx: number) => {
    const content = screen.getByTestId('coach-sheet-content');
    // jsdom has no layout: the grabber (20) + the border (1) sit above the content.
    Object.defineProperty(content, 'offsetTop', { configurable: true, value: 20 });
    Object.defineProperty(content, 'offsetHeight', { configurable: true, value: contentPx });
    Object.defineProperty(screen.getByTestId('coach-sheet'), 'clientTop', { configurable: true, value: 1 });
    act(() => callbacks.forEach((cb) => cb()));
  };
}

const peekVar = () => screen.getByTestId('coach-shell').style.getPropertyValue('--coach-play-peek');

describe('CoachShell', () => {
  it('starts at peek with the whole board and its move strip', () => {
    render(<Harness />);
    expect(detent()).toBe('peek');
    expect(screen.getByTestId('board')).toBeTruthy();
    expect(screen.getByTestId('strip')).toBeTruthy();
    expect(screen.queryByTestId('mini-board')).toBeNull();
    // Sized by CSS: the peek's calc(), no measured px.
    expect(screen.getByTestId('coach-sheet').style.height).toContain('100cqw');
  });

  it('focusing the composer pins a mini-board; tapping it returns to peek', () => {
    render(<Harness />);
    fireEvent.focus(screen.getByLabelText('composer'));
    expect(detent()).toBe('full');
    // The board is still there, pinned small, and the strip steps aside.
    expect(screen.getByTestId('board')).toBeTruthy();
    expect(screen.queryByTestId('strip')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: coach.showBoard }));
    expect(detent()).toBe('peek');
  });

  it('the grabber is a labelled button: tap toggles, arrows expand / collapse', () => {
    render(<Harness />);
    const grabber = screen.getByTestId('sheet-grabber');
    expect(grabber.getAttribute('aria-label')).toBe(coach.sheetExpand);
    fireEvent.click(grabber);
    expect(detent()).toBe('half');
    expect(grabber.getAttribute('aria-label')).toBe(coach.sheetCollapse);
    fireEvent.keyDown(grabber, { key: 'ArrowUp' });
    expect(detent()).toBe('full');
    fireEvent.keyDown(grabber, { key: 'ArrowDown' });
    fireEvent.keyDown(grabber, { key: 'ArrowDown' });
    expect(detent()).toBe('peek');
  });

  it('explore keeps the 232 peek floor and a flexible board', () => {
    render(<Harness />);
    expect(screen.getByTestId('coach-sheet').style.height).toContain(`${PEEK_MIN_PX}px`);
    expect(screen.getByTestId('coach-board-box').style.height).toBe('');
    expect(screen.getByTestId('sheet-grabber').className).toContain('h-11');
  });

  it('play: the peek hugs the action bar, a 20 px grabber, the board box is sized by CSS', () => {
    render(<Harness peekPx={PLAY_PEEK_PX} />);
    const sheet = screen.getByTestId('coach-sheet');
    expect(sheet.style.height).toContain(`${PLAY_PEEK_PX}px`);
    expect(sheet.style.height).not.toContain(`${PEEK_MIN_PX}px`);
    expect(screen.getByTestId('sheet-grabber').className).toContain('h-5');
    expect(screen.getByTestId('coach-board-box').style.height).toContain('100cqw');
    // The coach row flexes into what the board leaves, never under its minimum.
    expect((screen.getByTestId('coach-row').parentElement as HTMLElement).style.minHeight).toBe('88px');
    // At half the grabber is full height again.
    fireEvent.click(screen.getByTestId('sheet-grabber'));
    expect(screen.getByTestId('sheet-grabber').className).toContain('h-11');
  });

  it('play: the measured sheet content reaches --coach-play-peek; sheet and board box read it', () => {
    const resize = mockResizeObserver();
    render(<Harness peekPx={PLAY_PEEK_PX + PLAY_COMPOSER_PX} />);
    // Before a measurement: the fallback constant.
    expect(peekVar()).toBe(`${PLAY_PEEK_PX + PLAY_COMPOSER_PX}px`);
    // The action bar (64) + a composer grown by a voice notice (74 + 32).
    resize(64 + 74 + 32);
    expect(peekVar()).toBe('191px');
    expect(screen.getByTestId('coach-sheet').style.height).toContain('var(--coach-play-peek');
    expect(screen.getByTestId('coach-board-box').style.height).toContain('var(--coach-play-peek');
    // At peek the content keeps its natural height: the buttons are never squeezed.
    expect(screen.getByTestId('coach-sheet-content').className).toContain('shrink-0');
    expect(screen.getByTestId('coach-sheet-content').className).not.toContain('min-h-0');
  });

  it('play: away from peek the content fills the sheet and the last measurement holds', () => {
    const resize = mockResizeObserver();
    render(<Harness peekPx={PLAY_PEEK_PX} />);
    resize(64);
    expect(peekVar()).toBe('85px');
    fireEvent.click(screen.getByTestId('sheet-grabber'));
    expect(detent()).toBe('half');
    expect(screen.getByTestId('coach-sheet-content').className).toContain('flex-1');
    expect(peekVar()).toBe('85px');
  });

  it('explore sets no play peek variable', () => {
    mockResizeObserver();
    render(<Harness />);
    expect(peekVar()).toBe('');
    expect(screen.getByTestId('coach-sheet-content').className).toContain('flex-1');
  });
});
