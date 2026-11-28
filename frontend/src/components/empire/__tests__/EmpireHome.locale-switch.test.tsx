/**
 * @vitest-environment jsdom
 *
 * The CE home is a client tree, so a provider locale swap (LocaleProvider's
 * instant switch) re-translates it in place: same DOM nodes, client state kept,
 * locale-dependent data (the gamification rank name) follows the hook locale.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
}));

import EmpireHomePage from '../EmpireHomePage';
import EmpireCoachHome from '../EmpireCoachHome';
import type { CEStudentProfile } from '@/lib/chess-empire-client';
import type { GamificationProfile } from '@/lib/gamification/profile';
import { IntlWrapper, tr, type TestLocale } from './intl';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderSwitchable(ui: React.ReactElement) {
  const view = render(<IntlWrapper locale="ru">{ui}</IntlWrapper>);
  const switchTo = (locale: TestLocale) =>
    view.rerender(<IntlWrapper locale={locale}>{ui}</IntlWrapper>);
  return { ...view, switchTo };
}

const profile: CEStudentProfile = {
  id: 'stu-1',
  first_name: 'Ali',
  last_name: 'M.',
  branch_id: 'br-1',
  status: 'active',
  date_of_birth: null,
  current_rating: 856,
  current_level: 3,
  current_lesson: 40,
  total_lessons: 120,
};

const gamification: GamificationProfile = {
  linked: true,
  xp: 120,
  coins: 15,
  rank: { code: 'knight', name_ru: 'Конь-ru', name_kk: 'Ат-kk', name_en: 'Knight-en' },
  rank_progress: { pct: 40, xp_into_rank: 20, xp_for_next: 50, next_code: 'rook', next_min_xp: 170 },
  streak: { current_weeks: 2, best_weeks: 3, last_active_week: null, next_milestone: null },
  stats: { tournaments_played: 4, wins_total: 9 },
  legion: null,
  trophies: [],
};

describe('CE home — in-place locale switch', () => {
  it('EmpireHomePage re-translates ru→kz without remounting', () => {
    const { getByTestId, switchTo } = renderSwitchable(
      <EmpireHomePage
        state="verified"
        studentDisplayName="Ali"
        profile={profile}
        ratings={[]}
        rank={{ branch_rank: null, school_rank: null, branch_size: null, school_size: null }}
        gamification={gamification}
        achievements={[]}
      />,
    );
    const root = getByTestId('empire-home');
    const greeting = getByTestId('empire-home-greeting');
    const chips = getByTestId('empire-gamification-chips');
    expect(greeting.textContent).toBe(tr('empire', 'ru')('welcomeBackNamed', { name: 'Ali' }));
    expect(chips.textContent).toContain('Конь-ru');
    expect(getByTestId('empire-achievements').textContent).toContain(
      tr('empire', 'ru')('achievementsTitle'),
    );

    switchTo('kz');

    expect(getByTestId('empire-home')).toBe(root);
    expect(getByTestId('empire-home-greeting')).toBe(greeting);
    expect(greeting.textContent).toBe(tr('empire', 'kz')('welcomeBackNamed', { name: 'Ali' }));
    expect(chips.textContent).toContain('Ат-kk');
    expect(chips.textContent).not.toContain('Конь-ru');
    expect(getByTestId('empire-achievements').textContent).toContain(
      tr('empire', 'kz')('achievementsTitle'),
    );
  });

  it('keeps the pending-confirm banner state across the switch', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false })));
    const { switchTo } = renderSwitchable(
      <EmpireHomePage state="pending_confirm" studentDisplayName="Ali" />,
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('empire-pending-confirm-yes'));
    });
    const error = screen.getByTestId('empire-pending-error');
    const banner = screen.getByTestId('empire-pending-confirm');
    expect(banner.textContent).toContain(tr('empire', 'ru')('pendingConfirmYes'));

    switchTo('kz');

    expect(screen.getByTestId('empire-pending-error')).toBe(error);
    expect(banner.textContent).toContain(tr('empire', 'kz')('pendingConfirmTitle', { name: 'Ali' }));
    expect(banner.textContent).toContain(tr('empire', 'kz')('pendingConfirmYes'));
  });

  it('EmpireCoachHome re-translates ru→kz without remounting', () => {
    const { getByTestId, switchTo } = renderSwitchable(
      <EmpireCoachHome coachDisplayName="Chingis" />,
    );
    const root = getByTestId('empire-home-coach');
    expect(root.textContent).toContain(tr('empire', 'ru')('coachWelcomeNamed', { name: 'Chingis' }));

    switchTo('kz');

    expect(getByTestId('empire-home-coach')).toBe(root);
    expect(root.textContent).toContain(tr('empire', 'kz')('coachWelcomeNamed', { name: 'Chingis' }));
    expect(root.textContent).not.toContain(
      tr('empire', 'ru')('coachWelcomeNamed', { name: 'Chingis' }),
    );
  });
});
