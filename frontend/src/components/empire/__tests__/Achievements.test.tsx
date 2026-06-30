/**
 * @vitest-environment jsdom
 *
 * Server-component tests for Achievements. Verifies empty state, grid
 * rendering, the overflow "+N more" hint, and the icon / emoji fallback.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${Object.entries(opts).map(([k, v]) => `${k}=${v}`).join(',')}` : key,
}));

import Achievements from '../Achievements';
import type { CEAchievement } from '@/lib/chess-empire-client';

afterEach(() => {
  cleanup();
});

function makeAchievements(n: number, withIcon = false): CEAchievement[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `ach-${i}`,
    name: `Trophy ${i}`,
    earned_at: '2026-05-01T00:00:00Z',
    icon_url: withIcon ? `https://cdn/icon-${i}.png` : null,
  }));
}

describe('Achievements', () => {
  it('renders empty state when achievements is []', async () => {
    const ui = await Achievements({ achievements: [] });
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-achievements-empty')).toBeTruthy();
    expect(queryByTestId('empire-achievements-grid')).toBeNull();
  });

  it('renders grid for ≤9 achievements without "+N more"', async () => {
    const ui = await Achievements({ achievements: makeAchievements(5) });
    const { getByTestId, queryByTestId, getAllByTestId } = render(ui);
    expect(getByTestId('empire-achievements-grid')).toBeTruthy();
    expect(getAllByTestId('empire-achievement-card')).toHaveLength(5);
    expect(queryByTestId('empire-achievements-more')).toBeNull();
  });

  it('renders 9 cards + "+N more" when >9 achievements', async () => {
    const ui = await Achievements({ achievements: makeAchievements(14) });
    const { getByTestId, getAllByTestId } = render(ui);
    expect(getAllByTestId('empire-achievement-card')).toHaveLength(9);
    const more = getByTestId('empire-achievements-more');
    expect(more.textContent).toContain('count=5');
  });

  it('renders icon_url when present', async () => {
    const ui = await Achievements({ achievements: makeAchievements(1, true) });
    const { getByTestId, queryByTestId } = render(ui);
    const icon = getByTestId('empire-achievement-icon') as HTMLImageElement;
    expect(icon.src).toContain('https://cdn/icon-0.png');
    expect(queryByTestId('empire-achievement-fallback')).toBeNull();
  });

  it('renders 🏆 fallback when icon_url is missing', async () => {
    const ui = await Achievements({ achievements: makeAchievements(1, false) });
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-achievement-fallback').textContent).toBe('🏆');
    expect(queryByTestId('empire-achievement-icon')).toBeNull();
  });
});
