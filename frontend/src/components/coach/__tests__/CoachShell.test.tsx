/**
 * @vitest-environment jsdom
 */
import React, { useReducer } from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';
import CoachShell from '../CoachShell';
import { sheetReducer, MOVE_STRIP_PX } from '@/lib/coach/sheet-detent';

const coach = en.coach;

function Harness() {
  const [detent, dispatch] = useReducer(sheetReducer, 'peek');
  return (
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <CoachShell
        bar={<header>bar</header>}
        board={<div data-testid="board" />}
        below={<div data-testid="strip" />}
        stageChrome={MOVE_STRIP_PX}
        detent={detent}
        onSheet={dispatch}
        sheet={<textarea aria-label="composer" onFocus={() => dispatch({ type: 'composer_focus' })} />}
        keyboard={{ open: false, top: 0, height: 0 }}
      />
    </NextIntlClientProvider>
  );
}

const detent = () => screen.getByTestId('coach-shell').dataset.detent;

afterEach(cleanup);

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
});
