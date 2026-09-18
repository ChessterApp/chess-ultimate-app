/**
 * @vitest-environment jsdom
 *
 * CETournamentsView — the vanilla-schedule port + one-click registration.
 *
 * Covers the design port (branch accordion, roster rendering, localization
 * across en/ru/kz and every visitor state) and the one allowed functional
 * difference: one-click registration with an optimistic ✅ + roster update,
 * failure revert, logged-out prompt, and the `?tournament=<id>` deep link.
 */
import { describe, it, expect, afterEach, vi, beforeEach } from 'vitest';
import React from 'react';

// The family bar (2+ members) renders AddFamilyMember, which uses the app
// router. Stub it so the component tree mounts without a router provider.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
  within,
} from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';
import CETournamentsView, {
  type CETournamentCard,
  type CEViewer,
} from '../CETournamentsView';

const CATALOGS = { en, ru, kz } as const;

const BRANCH = { id: 'br-1', name: 'Almaty Arena' };

function renderView(
  viewer: CEViewer,
  tournaments: CETournamentCard[],
  {
    locale = 'en' as keyof typeof CATALOGS,
    branches = [BRANCH],
    deepLinkTournamentId = null as string | null,
  } = {},
) {
  return render(
    <NextIntlClientProvider
      locale={locale}
      messages={CATALOGS[locale] as Record<string, unknown>}
    >
      <CETournamentsView
        tournaments={tournaments}
        branches={branches}
        viewer={viewer}
        deepLinkTournamentId={deepLinkTournamentId}
      />
    </NextIntlClientProvider>,
  );
}

function makeCard(over: Partial<CETournamentCard> = {}): CETournamentCard {
  return {
    id: 't-1',
    name: 'Spring Open',
    info: null,
    tournament_date: '2026-03-14',
    start_time: '10:30:00',
    time_format: 'Blitz 5+3',
    registration_fee: 0,
    rounds: 7,
    capacity: 20,
    status: 'open',
    registered_count: 5,
    branch_id: BRANCH.id,
    branch_name: BRANCH.name,
    registration_deadline: null,
    roster: ['Aida Bekova', 'Timur Ali'],
    registration_id: null,
    is_registered: false,
    registrations: [],
    ...over,
  };
}

/** Expand the (single) branch accordion so its panels render. */
function expandBranch() {
  fireEvent.click(screen.getByText(BRANCH.name));
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('CETournamentsView — localization & structure', () => {
  it('renders the English header, subtitle and empty state', () => {
    renderView({ state: 'logged_out' }, [], { branches: [] });
    expect(screen.getByText(en.ceTournaments.title)).toBeTruthy();
    expect(screen.getByText(en.ceTournaments.subtitle)).toBeTruthy();
    expect(screen.getByText(en.ceTournaments.empty)).toBeTruthy();
  });

  it('renders the Russian header when locale is ru', () => {
    renderView({ state: 'logged_out' }, [], { branches: [], locale: 'ru' });
    expect(screen.getByText(ru.ceTournaments.title)).toBeTruthy();
    expect(screen.getByText(ru.ceTournaments.subtitle)).toBeTruthy();
    expect(screen.queryByText('Tournaments')).toBeNull();
  });

  it('renders the Kazakh header when locale is kz', () => {
    renderView({ state: 'logged_out' }, [], { branches: [], locale: 'kz' });
    expect(screen.getByText(kz.ceTournaments.title)).toBeTruthy();
    expect(screen.getByText(kz.ceTournaments.subtitle)).toBeTruthy();
  });

  it('shows a branch card with a localized upcoming count badge', () => {
    renderView({ state: 'logged_out' }, [makeCard()]);
    expect(screen.getByText(BRANCH.name)).toBeTruthy();
    // "1 upcoming" (en). The branch starts collapsed.
    expect(screen.getByText('1 upcoming')).toBeTruthy();
  });

  it('renders card labels, roster and register action once expanded (verified)', () => {
    renderView({ state: 'verified', studentName: 'Aidos' }, [makeCard()]);
    expandBranch();
    expect(screen.getByText(en.ceTournaments.date)).toBeTruthy();
    expect(screen.getByText(en.ceTournaments.rounds)).toBeTruthy();
    expect(screen.getByText(en.ceTournaments.rosterLabel)).toBeTruthy();
    // Roster full names render.
    expect(screen.getByText('Aida Bekova')).toBeTruthy();
    expect(screen.getByText('Timur Ali')).toBeTruthy();
    expect(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    ).toBeTruthy();
  });

  it('shows the full status pill and disabled action when at capacity', () => {
    renderView({ state: 'verified', studentName: 'Aidos' }, [
      makeCard({ registered_count: 20, capacity: 20 }),
    ]);
    expandBranch();
    const btn = screen.getByRole('button', {
      name: en.ceTournaments.tournamentFull,
    }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it('shows registered state + cancel action for an already-registered member', () => {
    renderView({ state: 'verified', studentName: 'Aidos' }, [
      makeCard({ registration_id: 'reg-1' }),
    ]);
    expandBranch();
    expect(screen.getByText(en.ceTournaments.registered)).toBeTruthy();
    expect(
      screen.getByRole('button', {
        name: en.ceTournaments.cancelRegistration,
      }),
    ).toBeTruthy();
  });
});

describe('CETournamentsView — one-click registration', () => {
  it('optimistically registers: button flips to ✓ and the member joins the roster', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ registration_id: 'reg-9', registered_count: 6 }),
    });
    renderView({ state: 'verified', studentName: 'Nurlan Sat' }, [makeCard()]);
    expandBranch();

    fireEvent.click(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    );

    // Optimistic roster insert is immediate.
    expect(screen.getByText('Nurlan Sat')).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText(en.ceTournaments.registered)).toBeTruthy();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chess-empire/tournaments/t-1/register',
      { method: 'POST' },
    );
    // Cancel affordance is now present.
    expect(
      screen.getByRole('button', {
        name: en.ceTournaments.cancelRegistration,
      }),
    ).toBeTruthy();
  });

  it('reverts the optimistic state and shows an error when the server rejects', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'full', message: 'full' }),
    });
    renderView({ state: 'verified', studentName: 'Nurlan Sat' }, [makeCard()]);
    expandBranch();

    fireEvent.click(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    );

    await waitFor(() => {
      expect(screen.getByText(en.ceTournaments.errors.full)).toBeTruthy();
    });
    // Reverted: still a Register button, member no longer in the roster.
    expect(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    ).toBeTruthy();
    expect(screen.queryByText('Nurlan Sat')).toBeNull();
  });

  it('shows the localized no_razryad message when the server rejects with that reason', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: 'no_razryad', message: 'server copy' }),
    });
    renderView({ state: 'verified', studentName: 'Nurlan Sat' }, [makeCard()]);
    expandBranch();

    fireEvent.click(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(en.ceTournaments.errors.no_razryad),
      ).toBeTruthy();
    });
    // Reverted to the register state; the localized copy (not the raw server
    // message) is shown.
    expect(screen.queryByText('server copy')).toBeNull();
    expect(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    ).toBeTruthy();
  });

  it('shows the Russian no_razryad message under the ru locale', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: 'no_razryad', message: 'server copy' }),
    });
    renderView({ state: 'verified', studentName: 'Nurlan Sat' }, [makeCard()], {
      locale: 'ru',
    });
    // Under ru the branch header renders its localized name.
    fireEvent.click(
      screen.getByText(ru.ceTournaments.branchNames['Almaty Arena']),
    );

    fireEvent.click(
      screen.getByRole('button', { name: ru.ceTournaments.register }),
    );

    await waitFor(() => {
      expect(
        screen.getByText(ru.ceTournaments.errors.no_razryad),
      ).toBeTruthy();
    });
  });

  it('prompts sign-in for a logged-out visitor instead of registering', () => {
    renderView({ state: 'logged_out' }, [makeCard()]);
    expandBranch();

    fireEvent.click(
      screen.getByRole('button', { name: en.ceTournaments.register }),
    );

    expect(screen.getByText(en.ceTournaments.loggedOutNotice)).toBeTruthy();
    // The in-panel sign-in link is present and no register request was made.
    const links = screen.getAllByRole('link', {
      name: `${en.ceTournaments.signInToRegister} →`,
    });
    expect(links.length).toBeGreaterThan(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('CETournamentsView — razryad eligibility note', () => {
  it('shows the "razryad holders only" badge for a Турнир Разрядников card', () => {
    renderView({ state: 'verified', studentName: 'Aidos' }, [
      makeCard({ name: 'Турнир Разрядников — Almaty' }),
    ]);
    expandBranch();
    expect(screen.getByText(en.ceTournaments.razryadOnly)).toBeTruthy();
  });

  it('omits the badge for a regular tournament', () => {
    renderView({ state: 'verified', studentName: 'Aidos' }, [
      makeCard({ name: 'Spring Open' }),
    ]);
    expandBranch();
    expect(screen.queryByText(en.ceTournaments.razryadOnly)).toBeNull();
  });
});

describe('CETournamentsView — deep link', () => {
  it('auto-expands the branch of the deep-linked tournament', () => {
    const cards = [
      makeCard({ id: 't-1', name: 'Spring Open' }),
      makeCard({
        id: 't-2',
        name: 'Winter Cup',
        branch_id: 'br-2',
        branch_name: 'Debut',
      }),
    ];
    renderView({ state: 'logged_out' }, cards, {
      branches: [BRANCH, { id: 'br-2', name: 'Debut' }],
      deepLinkTournamentId: 't-2',
    });

    // The deep-linked branch is expanded → its panel (and roster) render;
    // the other branch stays collapsed.
    const winter = screen.getByText('Winter Cup');
    expect(winter).toBeTruthy();
    const highlighted = winter.closest('.tournament-row');
    expect(highlighted?.className).toContain('highlighted');
    expect(screen.queryByText('Spring Open')).toBeNull();
  });
});

describe('CETournamentsView — family (multi-member) registration', () => {
  const CHILD = { studentId: 'stu-child', name: 'Alikhan', relationship: 'child' as const };
  const SELF = { studentId: 'stu-self', name: 'Parent P', relationship: 'self' as const };

  function familyViewer(members = [CHILD, SELF]): CEViewer {
    return { state: 'verified', studentName: 'Parent P', members };
  }

  /** The expanded tournament panel element, for scoped queries. */
  function panel(id = 't-1'): HTMLElement {
    return document.querySelector(
      `[data-tournament-id="${id}"]`,
    ) as HTMLElement;
  }

  it('shows no picker for a single verified member (regression bar)', () => {
    renderView(familyViewer([SELF]), [makeCard()]);
    expandBranch();
    // Single member → the legacy one-click Register button, no picker group.
    expect(
      within(panel()).getByRole('button', { name: en.ceTournaments.register }),
    ).toBeTruthy();
    expect(
      within(panel()).queryByRole('group', {
        name: en.ceTournaments.pickMember,
      }),
    ).toBeNull();
    // No family bar chrome for a single member.
    expect(screen.queryByText(en.ceTournaments.familyTitle)).toBeNull();
  });

  it('single-member register sends no request body (byte-compatible)', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ registration_id: 'reg-9', registered_count: 6 }),
    });
    renderView(familyViewer([SELF]), [makeCard()]);
    expandBranch();
    fireEvent.click(
      within(panel()).getByRole('button', { name: en.ceTournaments.register }),
    );
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chess-empire/tournaments/t-1/register',
        { method: 'POST' },
      );
    });
  });

  it('opens a picker for 2+ members and POSTs the picked student_id', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ registration_id: 'reg-child', registered_count: 6 }),
    });
    renderView(familyViewer(), [makeCard()]);
    expandBranch();

    // Register opens the picker rather than registering directly.
    fireEvent.click(
      within(panel()).getByRole('button', { name: en.ceTournaments.register }),
    );
    const picker = within(panel()).getByRole('group', {
      name: en.ceTournaments.pickMember,
    });
    // Both members are offered (neither is registered yet).
    fireEvent.click(within(picker).getByRole('button', { name: /Alikhan/ }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chess-empire/tournaments/t-1/register',
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ student_id: 'stu-child' }),
        },
      );
    });
  });

  it('renders a per-member chip for each registered child', () => {
    renderView(familyViewer(), [
      makeCard({
        registrations: [{ studentId: 'stu-child', registrationId: 'reg-child' }],
      }),
    ]);
    expandBranch();
    // A "✓ Alikhan" chip appears in the card.
    expect(within(panel()).getByText(/✓\s*Alikhan/)).toBeTruthy();
    // The still-unregistered parent is offered in the picker after opening it.
    fireEvent.click(
      within(panel()).getByRole('button', { name: en.ceTournaments.register }),
    );
    const picker = within(panel()).getByRole('group', {
      name: en.ceTournaments.pickMember,
    });
    expect(within(picker).getByRole('button', { name: /Parent P/ })).toBeTruthy();
    expect(within(picker).queryByRole('button', { name: /Alikhan/ })).toBeNull();
  });

  it('cancel targets the picked member with a DELETE + student_id body', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    renderView(familyViewer(), [
      makeCard({
        roster: ['Alikhan', 'Parent P'],
        registrations: [
          { studentId: 'stu-child', registrationId: 'reg-child' },
          { studentId: 'stu-self', registrationId: 'reg-self' },
        ],
      }),
    ]);
    expandBranch();

    // Cancel the child's chip specifically.
    const cancelChild = within(panel()).getByRole('button', {
      name: new RegExp(`${en.ceTournaments.cancelRegistration}.*Alikhan`),
    });
    fireEvent.click(cancelChild);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/chess-empire/tournaments/t-1/register',
        {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ student_id: 'stu-child' }),
        },
      );
    });
  });

  it('surfaces a localized message on a forbidden_student response', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ error: 'forbidden_student' }),
    });
    renderView(familyViewer(), [makeCard()]);
    expandBranch();
    fireEvent.click(
      within(panel()).getByRole('button', { name: en.ceTournaments.register }),
    );
    const picker = within(panel()).getByRole('group', {
      name: en.ceTournaments.pickMember,
    });
    fireEvent.click(within(picker).getByRole('button', { name: /Alikhan/ }));

    await waitFor(() => {
      expect(
        within(panel()).getByText(en.ceTournaments.errors.forbidden_student),
      ).toBeTruthy();
    });
  });

  it('renders the family bar with each member and its relationship tag', () => {
    renderView(familyViewer(), [makeCard()]);
    expect(screen.getByText(en.ceTournaments.familyTitle)).toBeTruthy();
    // Both members are listed in the bar with their relationship tags.
    expect(screen.getAllByText(/Alikhan/).length).toBeGreaterThan(0);
    expect(
      screen.getByRole('button', {
        name: new RegExp(en.ceTournaments.addFamilyMember),
      }),
    ).toBeTruthy();
  });
});

describe('CETournamentsView — cancel', () => {
  it('cancels an existing registration back to the register state', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    renderView({ state: 'verified', studentName: 'Aidos' }, [
      makeCard({ registration_id: 'reg-1', roster: ['Aidos'] }),
    ]);
    expandBranch();

    fireEvent.click(
      screen.getByRole('button', {
        name: en.ceTournaments.cancelRegistration,
      }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole('button', { name: en.ceTournaments.register }),
      ).toBeTruthy();
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chess-empire/tournaments/t-1/register',
      { method: 'DELETE' },
    );
    // The roster panel no longer lists the cancelled member.
    const roster = document.querySelector('.roster');
    expect(within(roster as HTMLElement).queryByText('Aidos')).toBeNull();
  });
});
