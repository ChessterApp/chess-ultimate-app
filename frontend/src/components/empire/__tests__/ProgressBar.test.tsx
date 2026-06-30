/**
 * @vitest-environment jsdom
 *
 * Server-component tests for ProgressBar. Verifies fill percentage, the
 * "?" fallback for missing values, and clamping at 100%.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${Object.entries(opts).map(([k, v]) => `${k}=${v}`).join(',')}` : key,
}));

import ProgressBar from '../ProgressBar';

afterEach(() => {
  cleanup();
});

describe('ProgressBar', () => {
  it('renders correct percentage for current/total', async () => {
    const ui = await ProgressBar({ current: 6, total: 24, level: 2 });
    const { getByTestId } = render(ui);
    const fill = getByTestId('empire-progress-fill') as HTMLDivElement;
    expect(fill.style.width).toBe('25%');
    const track = getByTestId('empire-progress-track');
    expect(track.getAttribute('aria-valuenow')).toBe('25');
  });

  it('shows `?` not NaN when total is missing', async () => {
    const ui = await ProgressBar({ current: 6, total: null, level: null });
    const { getByTestId } = render(ui);
    const label = getByTestId('empire-progress-label');
    expect(label.textContent).not.toContain('NaN');
    expect(label.textContent).toContain('total=?');
    expect(label.textContent).toContain('level=?');
    const fill = getByTestId('empire-progress-fill') as HTMLDivElement;
    expect(fill.style.width).toBe('0%');
  });

  it('shows `?` for missing current too', async () => {
    const ui = await ProgressBar({ current: null, total: 24, level: 1 });
    const { getByTestId } = render(ui);
    const label = getByTestId('empire-progress-label');
    expect(label.textContent).toContain('current=?');
  });

  it('clamps at 100% when current > total', async () => {
    const ui = await ProgressBar({ current: 30, total: 24, level: 4 });
    const { getByTestId } = render(ui);
    const fill = getByTestId('empire-progress-fill') as HTMLDivElement;
    expect(fill.style.width).toBe('100%');
  });

  it('shows 0% when total is zero (no divide-by-zero)', async () => {
    const ui = await ProgressBar({ current: 5, total: 0, level: 1 });
    const { getByTestId } = render(ui);
    const fill = getByTestId('empire-progress-fill') as HTMLDivElement;
    expect(fill.style.width).toBe('0%');
  });
});
