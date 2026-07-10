/**
 * @vitest-environment jsdom
 *
 * Tests for the coach-variant empire home. Verifies the avatar photo/initials
 * fallback, branch name, stat cards (total / with razryad / league breakdown),
 * bio, roster rendering, and the graceful empty state when no enrichment data
 * is supplied (CE API down).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';
import type { CEActiveStudent } from '@/lib/chess-empire-client';
import type { CoachHomeStats } from '@/lib/empire-coach-stats';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string, values?: Record<string, unknown>) => {
    if (!values) return key;
    return `${key}(${JSON.stringify(values)})`;
  },
}));

import EmpireCoachHome from '../EmpireCoachHome';

const roster: CEActiveStudent[] = [
  {
    id: 'stu-1',
    first_name: 'Aigerim',
    last_name: 'N',
    status: 'active',
    branch_id: 'br-1',
    coach_id: 'co-1',
    current_razryad: '3rd',
    current_league: 'A',
  },
  {
    id: 'stu-2',
    first_name: 'Bek',
    last_name: 'T',
    status: 'active',
    branch_id: 'br-1',
    coach_id: 'co-1',
    current_razryad: 'none',
    current_league: null,
  },
];

const stats: CoachHomeStats = {
  total: 2,
  withRazryad: 1,
  leagueBreakdown: [{ league: 'A', count: 1 }],
};

afterEach(cleanup);

describe('EmpireCoachHome', () => {
  it('renders photo avatar, branch, stats, bio and roster when data is present', async () => {
    const ui = await EmpireCoachHome({
      coachDisplayName: 'Chingis',
      photoUrl: 'https://cdn.example.com/chingis.jpg',
      bio: 'Grandmaster, 15 years coaching.',
      branchName: 'Debut Branch',
      stats,
      roster,
    });
    const { getByTestId, getAllByTestId, queryByTestId } = render(ui);

    const avatar = getByTestId('empire-coach-avatar') as HTMLImageElement;
    expect(avatar.tagName).toBe('IMG');
    expect(avatar.src).toContain('chingis.jpg');

    expect(getByTestId('empire-coach-branch').textContent).toContain('Debut Branch');
    expect(getByTestId('empire-coach-total').textContent).toBe('2');
    expect(getByTestId('empire-coach-razryad-count').textContent).toBe('1');
    expect(getByTestId('empire-coach-league-pill').textContent).toContain('A');
    expect(getByTestId('empire-coach-bio').textContent).toContain('Grandmaster');

    const rows = getAllByTestId('empire-coach-roster-row');
    expect(rows).toHaveLength(2);
    // First student has a real razryad; second's "none" is suppressed.
    expect(getAllByTestId('empire-coach-roster-razryad')).toHaveLength(1);
    expect(queryByTestId('empire-coach-roster-empty')).toBeNull();
  });

  it('falls back to an initials avatar and empty states with no enrichment', async () => {
    const ui = await EmpireCoachHome({ coachDisplayName: 'Chingis' });
    const { getByTestId } = render(ui);

    const avatar = getByTestId('empire-coach-avatar');
    expect(avatar.tagName).toBe('DIV');
    expect(avatar.textContent).toBe('C');
    expect(getByTestId('empire-coach-total').textContent).toBe('0');
    expect(getByTestId('empire-coach-roster-empty')).toBeTruthy();
  });
});
