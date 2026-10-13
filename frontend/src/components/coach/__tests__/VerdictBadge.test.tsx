/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, act } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import { VerdictBadge, VerdictToast } from '../VerdictBadge';

function wrap(node: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      {node}
    </NextIntlClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const blunder = { kind: 'blunder' as const, square: 'h4', san: 'h4', best: 'e4' };

describe('VerdictBadge', () => {
  it('sits on the destination square’s top-right corner, by orientation', () => {
    wrap(<VerdictBadge verdict={blunder} orientation="white" />);
    const badge = screen.getByTestId('verdict-badge');
    expect(badge.textContent).toBe('??');
    expect(badge.getAttribute('aria-label')).toBe('h4: blunder, better was e4');
    // h4 from white: column 7 (87.5%), row 4 (50%).
    expect(badge.style.left).toBe('calc(100% - 14px)');
    expect(badge.style.top).toBe('calc(50% - 8px)');
    cleanup();
    wrap(<VerdictBadge verdict={blunder} orientation="black" />);
    expect(screen.getByTestId('verdict-badge').style.left).toBe('calc(12.5% - 14px)');
  });

  it('a best move has no "better was"', () => {
    wrap(<VerdictBadge verdict={{ kind: 'best', square: 'f3', san: 'Nf3', best: 'Nf3' }} orientation="white" />);
    expect(screen.getByTestId('verdict-badge').getAttribute('aria-label')).toBe('Nf3: best move');
  });
});

describe('VerdictToast', () => {
  it('one line, then it goes away', () => {
    vi.useFakeTimers();
    const onDone = vi.fn();
    wrap(<VerdictToast verdict={blunder} onDone={onDone} />);
    expect(screen.getByRole('status').textContent).toContain('h4: blunder, better was e4');
    act(() => vi.advanceTimersByTime(3500));
    expect(onDone).toHaveBeenCalledTimes(1);
  });
});
