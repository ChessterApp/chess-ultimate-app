/**
 * @vitest-environment jsdom
 *
 * Tests for Achievements. Verifies empty state, grid
 * rendering, the overflow "+N more" hint, and the icon / emoji fallback.
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { cleanup } from '@testing-library/react';
import { renderIntl, tr } from './intl';

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
  it('renders empty state when achievements is []', () => {
    const ui = React.createElement(Achievements, { achievements: [] });
    const { getByTestId, queryByTestId } = renderIntl(ui);
    expect(getByTestId('empire-achievements-empty')).toBeTruthy();
    expect(queryByTestId('empire-achievements-grid')).toBeNull();
  });

  it('renders grid for ≤9 achievements without "+N more"', () => {
    const ui = React.createElement(Achievements, { achievements: makeAchievements(5) });
    const { getByTestId, queryByTestId, getAllByTestId } = renderIntl(ui);
    expect(getByTestId('empire-achievements-grid')).toBeTruthy();
    expect(getAllByTestId('empire-achievement-card')).toHaveLength(5);
    expect(queryByTestId('empire-achievements-more')).toBeNull();
  });

  it('renders 9 cards + "+N more" when >9 achievements', () => {
    const ui = React.createElement(Achievements, { achievements: makeAchievements(14) });
    const { getByTestId, getAllByTestId } = renderIntl(ui);
    expect(getAllByTestId('empire-achievement-card')).toHaveLength(9);
    const more = getByTestId('empire-achievements-more');
    expect(more.textContent).toBe(tr('empire')('achievementsMore', { count: 5 }));
  });

  it('renders icon_url when present', () => {
    const ui = React.createElement(Achievements, { achievements: makeAchievements(1, true) });
    const { getByTestId, queryByTestId } = renderIntl(ui);
    const icon = getByTestId('empire-achievement-icon') as HTMLImageElement;
    expect(icon.src).toContain('https://cdn/icon-0.png');
    expect(queryByTestId('empire-achievement-fallback')).toBeNull();
  });

  it('renders 🏆 fallback when icon_url is missing', () => {
    const ui = React.createElement(Achievements, { achievements: makeAchievements(1, false) });
    const { getByTestId, queryByTestId } = renderIntl(ui);
    expect(getByTestId('empire-achievement-fallback').textContent).toBe('🏆');
    expect(queryByTestId('empire-achievement-icon')).toBeNull();
  });
});
