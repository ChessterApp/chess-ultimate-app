/**
 * @vitest-environment jsdom
 *
 * Puzzle Rush × Chess Empire school ranking: School / Branch leaderboard tabs
 * (survival + signed in only) and the results modal's school outcome block.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import Leaderboard from '../Leaderboard';
import ResultsModal from '../ResultsModal';
import type { RushMode, RushResults, SchoolOutcome } from '@/lib/puzzle-rush/types';

const auth = () => ({ getToken: async () => 'jwt' });
const fetchMock = vi.fn();

type Reply = { status?: number; body: unknown };
/** Route each request by URL: `(url) => reply`. */
function serve(handler: (url: URL, init: RequestInit) => Reply) {
  fetchMock.mockImplementation(async (u: string, init: RequestInit) => {
    const { status = 200, body } = handler(new URL(u, 'http://x'), init);
    return new Response(JSON.stringify(body), { status });
  });
}
const calls = () => fetchMock.mock.calls.map(([u]) => new URL(u as string, 'http://x'));
const schoolCalls = () => calls().filter((u) => ['school', 'branch'].includes(u.searchParams.get('scope') ?? ''));

const KIDS = [
  { student_id: 'stu-a', first_name: 'Aruzhan', last_name: 'K', branch_id: 'b1' },
  { student_id: 'stu-b', first_name: 'Timur', last_name: 'K', branch_id: 'b2' },
];

function board(scope: string, period: string, extra: Record<string, unknown> = {}) {
  return {
    mode: 'survival', scope, period, student_id: 'stu-a', branch_id: null, window_start: null, total_count: 3,
    entries: [
      { rank: 1, name: 'Dana S.', branch_name: 'Almaty Center', score: 40, achieved_at: null, is_self: false, source: 'chesster' },
      { rank: 2, name: 'Aruzhan K.', branch_name: 'Almaty Center', score: 31, achieved_at: null, is_self: true, source: 'chesster' },
    ],
    me: { score: 31, rank: 2 },
    ...extra,
  };
}

function withIntl(node: React.ReactNode) {
  return render(<NextIntlClientProvider locale="en" messages={en}>{node}</NextIntlClientProvider>);
}

function renderBoard(props: Partial<React.ComponentProps<typeof Leaderboard>> = {}) {
  return withIntl(
    <Leaderboard mode="survival" auth={auth} isGuest={false} userId="u1" signInHref="/sign-in" {...props} />,
  );
}

const tabNames = () => screen.getAllByRole('tab').map((b) => b.textContent);

beforeEach(() => {
  fetchMock.mockReset();
  global.fetch = fetchMock as unknown as typeof fetch;
  serve((url) => {
    const scope = url.searchParams.get('scope')!;
    if (scope === 'school' || scope === 'branch') return { body: board(scope, url.searchParams.get('period')!) };
    return { body: { mode: 'survival', period: 'daily', scope, entries: [], me: null } };
  });
});
afterEach(() => cleanup());

describe('Leaderboard school / branch scopes', () => {
  it.each<[RushMode, boolean, boolean]>([
    ['survival', false, true],
    ['survival', true, false],
    ['3min', false, false],
    ['5min', false, false],
  ])('mode %s, guest %s → school tabs %s', async (mode, isGuest, shown) => {
    renderBoard({ mode, isGuest });
    await screen.findByText(/No scores yet|Sign in/);
    expect(tabNames().includes('School')).toBe(shown);
    expect(tabNames().includes('Branch')).toBe(shown);
  });

  it('School: Week | Month | All-time periods, weekly maps to week, branch shown muted, self highlighted', async () => {
    renderBoard();
    fireEvent.click(screen.getByRole('tab', { name: 'Weekly' }));
    fireEvent.click(screen.getByRole('tab', { name: 'School' }));
    expect(tabNames()).toEqual(['Global', 'Personal', 'School', 'Branch', 'Week', 'Month', 'All-time']);
    expect(screen.getByRole('tab', { name: 'Week' }).getAttribute('aria-selected')).toBe('true');

    const self = (await screen.findByText('Aruzhan K.')).closest('li')!;
    expect(self.dataset.self).toBe('true');
    expect(screen.getByText('Dana S.').closest('li')!.dataset.self).toBeUndefined();
    expect(screen.getAllByText('Almaty Center')).toHaveLength(2);
    // Self is in the list: no pinned row.
    expect(screen.queryByTestId('lb-me')).toBeNull();

    fireEvent.click(screen.getByRole('tab', { name: 'Month' }));
    await waitFor(() => expect(schoolCalls().at(-1)!.searchParams.get('period')).toBe('month'));
    expect(schoolCalls().map((u) => u.searchParams.get('period'))).toEqual(['week', 'month']);
    expect(schoolCalls().every((u) => u.searchParams.get('mode') === 'survival')).toBe(true);
  });

  it('Branch: no branch name column; all-time carries over from the global board', async () => {
    renderBoard();
    fireEvent.click(screen.getByRole('tab', { name: 'All-time' }));
    fireEvent.click(screen.getByRole('tab', { name: 'Branch' }));
    await screen.findByText('Aruzhan K.');
    expect(screen.queryByText('Almaty Center')).toBeNull();
    expect(schoolCalls().at(-1)!.searchParams.get('scope')).toBe('branch');
    expect(schoolCalls().at(-1)!.searchParams.get('period')).toBe('all');
  });

  it('pins "me" when the student is outside the listed rows', async () => {
    serve((url) => ({
      body: board(url.searchParams.get('scope')!, 'week', {
        entries: [{ rank: 1, name: 'Dana S.', branch_name: null, score: 40, achieved_at: null, is_self: false, source: null }],
        me: { score: 3, rank: 57 },
      }),
    }));
    renderBoard({ initialScope: 'school' });
    const me = await screen.findByTestId('lb-me');
    expect(within(me).getByText('#57')).toBeTruthy();
    expect(within(me).getByText('You')).toBeTruthy();
  });

  it('403 not_linked: a short link-your-student message, no error', async () => {
    serve(() => ({ status: 403, body: { error: 'not_linked' } }));
    renderBoard({ initialScope: 'school' });
    expect(await screen.findByText('Link your Chess Empire student to see school ranks.')).toBeTruthy();
    expect(screen.queryByText("Couldn't load the leaderboard.")).toBeNull();
  });

  it.each([503, 502])('%s: school ranking unavailable', async (status) => {
    serve(() => ({ status, body: { error: 'school_unavailable' } }));
    renderBoard({ initialScope: 'branch' });
    expect(await screen.findByText('School ranking unavailable right now.')).toBeTruthy();
  });

  it('401: sign-in link', async () => {
    serve(() => ({ status: 401, body: { error: 'auth_required' } }));
    renderBoard({ initialScope: 'school' });
    expect((await screen.findByRole('link', { name: 'Sign in to see school rankings.' })).getAttribute('href')).toBe('/sign-in');
  });

  it('400 student_required: pick a student, refetch with student_id, then a switcher above the list', async () => {
    serve((url) => (url.searchParams.get('student_id')
      ? { body: board('school', 'week', { student_id: url.searchParams.get('student_id') }) }
      : { status: 400, body: { error: 'student_required', candidates: KIDS } }));
    renderBoard({ initialScope: 'school' });
    expect(await screen.findByText('Whose ranking?')).toBeTruthy();
    fireEvent.click(screen.getByRole('radio', { name: 'Timur K' }));

    await screen.findByText('Aruzhan K.');
    expect(schoolCalls().at(-1)!.searchParams.get('student_id')).toBe('stu-b');
    const switcher = screen.getByRole('radiogroup', { name: 'Whose ranking?' });
    expect(within(switcher).getByRole('radio', { name: 'Timur K' }).getAttribute('aria-checked')).toBe('true');

    fireEvent.click(within(switcher).getByRole('radio', { name: 'Aruzhan K' }));
    await waitFor(() => expect(schoolCalls().at(-1)!.searchParams.get('student_id')).toBe('stu-a'));
  });

  it('family students passed in show the switcher without a student_required round trip', async () => {
    renderBoard({ initialScope: 'school', students: KIDS });
    await screen.findByText('Aruzhan K.');
    expect(screen.getByRole('radiogroup', { name: 'Whose ranking?' })).toBeTruthy();
    // The server's remembered pick is the selected student.
    expect(screen.getByRole('radio', { name: 'Aruzhan K' }).getAttribute('aria-checked')).toBe('true');
  });

  it('falls back to Global when the mode stops being survival', async () => {
    const { rerender } = renderBoard({ initialScope: 'school' });
    await screen.findByText('Aruzhan K.');
    rerender(
      <NextIntlClientProvider locale="en" messages={en}>
        <Leaderboard mode="3min" auth={auth} isGuest={false} userId="u1" signInHref="/sign-in" initialScope="school" />
      </NextIntlClientProvider>,
    );
    expect(screen.getByRole('tab', { name: 'Global' }).getAttribute('aria-selected')).toBe('true');
    expect(tabNames()).not.toContain('School');
  });
});

const RESULTS: RushResults = {
  score: 31, is_new_pb: false, longest_streak: 9, highest_solved_rating: 1500, avg_ms_per_puzzle: 5000,
  duration_ms: 200000, personal_rank: 2, global_rank: { daily: 3, weekly: 12, all: 87 },
};
const RUN_ID = '11111111-2222-4333-8444-555555555555';

function results(school: SchoolOutcome | null | undefined, extra: Partial<React.ComponentProps<typeof ResultsModal>> = {}) {
  const onOpenBoard = vi.fn();
  withIntl(
    <ResultsModal
      mode="survival"
      score={31}
      tiles={[]}
      results={{ ...RESULTS, school }}
      endReason="strikes"
      isPb={false}
      isGuest={false}
      signInHref="/sign-in"
      onPlayAgain={vi.fn()}
      onNewRush={vi.fn()}
      onClose={vi.fn()}
      onOpenPuzzle={vi.fn()}
      school={{ runId: RUN_ID, auth, onOpenBoard }}
      {...extra}
    />,
  );
  return { onOpenBoard };
}

describe('ResultsModal school outcome', () => {
  it('needs_student: remembered pick pre-selected, Confirm claims, then shows the pushed outcome', async () => {
    serve((url, init) => {
      if (url.pathname.endsWith('/school-claim')) {
        return { body: { school: { status: 'pushed', student_id: JSON.parse(init.body as string).student_id, beaten: ['week', 'month'] } } };
      }
      return { body: board(url.searchParams.get('scope')!, 'week', { me: { score: 31, rank: url.searchParams.get('scope') === 'school' ? 7 : 2 } }) };
    });
    results({ status: 'needs_student', candidates: KIDS, last_student_id: 'stu-b' });

    expect(screen.getByText('Who played?')).toBeTruthy();
    expect(screen.getByRole('radio', { name: 'Timur K' }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('radio', { name: 'Aruzhan K' }).getAttribute('aria-checked')).toBe('false');
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));

    expect(await screen.findByText('New school best this month!')).toBeTruthy();
    const claim = fetchMock.mock.calls.find(([u]) => String(u).includes('/school-claim'))!;
    expect(String(claim[0])).toContain(`/runs/${RUN_ID}/school-claim`);
    expect(JSON.parse((claim[1] as RequestInit).body as string)).toEqual({ student_id: 'stu-b' });
    await waitFor(() => expect(screen.getByTestId('rush-school-rank').textContent).toBe('#7'));
    expect(screen.getByTestId('rush-branch-rank').textContent).toBe('#2');
  });

  it('needs_student: no valid remembered pick → Confirm disabled until a pick; Skip pushes nothing', () => {
    results({ status: 'needs_student', candidates: KIDS, last_student_id: 'gone' });
    const confirm = screen.getByRole('button', { name: 'Confirm' }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    fireEvent.click(screen.getByRole('radio', { name: 'Aruzhan K' }));
    expect(confirm.disabled).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Skip' }));
    expect(screen.queryByTestId('rush-school')).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('needs_student: a failed claim keeps the picker with a retry note', async () => {
    serve(() => ({ status: 403, body: { error: 'student_not_linked' } }));
    results({ status: 'needs_student', candidates: KIDS, last_student_id: 'stu-a' });
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(await screen.findByText("Couldn't save — try again.")).toBeTruthy();
    expect(screen.getByText('Who played?')).toBeTruthy();
  });

  it('pushed: widest beaten period, week ranks for the student from both boards, link to the School tab', async () => {
    const { onOpenBoard } = results({ status: 'pushed', student_id: 'stu-a', beaten: ['week', 'month', 'all'], best: null });
    expect(screen.getByText('New all-time school best!')).toBeTruthy();
    expect(screen.getByTestId('rush-school-rank').textContent).toBe('…');
    await waitFor(() => expect(screen.getByTestId('rush-school-rank').textContent).toBe('#2'));
    const boards = schoolCalls();
    expect(boards.map((u) => u.searchParams.get('scope')).sort()).toEqual(['branch', 'school']);
    expect(boards.every((u) => u.searchParams.get('period') === 'week' && u.searchParams.get('student_id') === 'stu-a')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'See the school leaderboard' }));
    expect(onOpenBoard).toHaveBeenCalledTimes(1);
  });

  it('pushed: a failed rank lookup shows a dash, not an error', async () => {
    serve(() => ({ status: 502, body: { error: 'school_unavailable' } }));
    results({ status: 'pushed', student_id: 'stu-a', beaten: ['week'] });
    expect(screen.getByText('New school best this week!')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('rush-school-rank').textContent).toBe('—'));
    expect(screen.getByTestId('rush-branch-rank').textContent).toBe('—');
  });

  it('not_best: a quiet line with the current school best', () => {
    results({ status: 'not_best', student_id: 'stu-a', best: { week: 40, month: 44, all: 52 } });
    expect(screen.getByTestId('rush-school').textContent).toBe('School best this week: 40');
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each<[string, SchoolOutcome | null | undefined]>([
    ['null', null],
    ['absent (finish pending)', undefined],
    ['unlinked', { status: 'unlinked' }],
    ['disabled', { status: 'disabled' }],
    ['error', { status: 'error', student_id: 'stu-a' }],
    ['0-score not_best', { status: 'not_best', student_id: null }],
  ])('%s: nothing school-related', (_, school) => {
    results(school);
    expect(screen.queryByTestId('rush-school')).toBeNull();
    expect(screen.queryByText(/school/i)).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('guests (no school prop) never render the block', () => {
    results({ status: 'pushed', student_id: 'stu-a', beaten: ['week'] }, { isGuest: true, school: undefined });
    expect(screen.queryByTestId('rush-school')).toBeNull();
  });
});
