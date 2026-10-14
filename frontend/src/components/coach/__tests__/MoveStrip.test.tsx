/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';
import MoveStrip from '../MoveStrip';

const coach = en.coach;

function renderStrip(props: Partial<React.ComponentProps<typeof MoveStrip>> = {}) {
  const handlers = { onJump: vi.fn(), onPrev: vi.fn(), onNext: vi.fn() };
  render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <MoveStrip moves={['e4', 'c5', 'Nf3']} currentIndex={1} {...handlers} {...props} />
    </NextIntlClientProvider>,
  );
  return handlers;
}

afterEach(cleanup);

describe('MoveStrip', () => {
  it('numbers the moves and marks the current one', () => {
    renderStrip();
    expect(screen.getByText('1.')).toBeTruthy();
    expect(screen.getByText('2.')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'c5' }).getAttribute('aria-current')).toBe('true');
  });

  it('tap jumps; ‹ › step', () => {
    const h = renderStrip();
    fireEvent.click(screen.getByRole('button', { name: 'Nf3' }));
    expect(h.onJump).toHaveBeenCalledWith(2);
    fireEvent.click(screen.getByRole('button', { name: coach.previousMove }));
    fireEvent.click(screen.getByRole('button', { name: coach.nextMove }));
    expect(h.onPrev).toHaveBeenCalledOnce();
    expect(h.onNext).toHaveBeenCalledOnce();
  });

  it('disables ‹ at the start and › at the end; says so when there are no moves', () => {
    renderStrip({ moves: [], currentIndex: -1 });
    expect(screen.getByText(coach.moveStripEmpty)).toBeTruthy();
    expect((screen.getByRole('button', { name: coach.previousMove }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole('button', { name: coach.nextMove }) as HTMLButtonElement).disabled).toBe(true);
  });
});
