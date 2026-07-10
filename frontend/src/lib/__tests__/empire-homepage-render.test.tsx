/**
 * @vitest-environment jsdom
 *
 * Tests for renderEmpireHomepage — the coach branch (Task 4) and the no_link
 * client-wrapper branch (Task 1). Verifies coaches never hit the student
 * profile API (which 404s for them) and render the coach variant instead of
 * the generic fallback, and that the no_link state is wrapped in the poller.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

const memberStore: { state: string; role: string; studentId: string | null } = {
  state: 'verified',
  role: 'coach',
  studentId: 'coach-uuid',
};
vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipState: vi.fn(async () => ({
    state: memberStore.state,
    role: memberStore.role,
    studentId: memberStore.studentId,
    memberId: memberStore.studentId ? 'mem-1' : null,
  })),
}));

const getStudentProfile = vi.fn(async () => ({ id: 'stu', first_name: 'S' }));
const getCoachProfile = vi.fn(async () => ({
  id: 'coach-uuid',
  first_name: 'Aigerim',
  last_name: 'Nur',
  branch_id: 'b1',
}));
const listBranches = vi.fn(async () => [{ id: 'b1', name: 'Debut Branch' }]);
const listActiveStudentsByCoach = vi.fn(async () => [
  {
    id: 'stu-1',
    first_name: 'A',
    last_name: 'B',
    status: 'active',
    branch_id: 'b1',
    coach_id: 'coach-uuid',
    current_razryad: '3rd',
    current_league: 'A',
  },
]);
vi.mock('@/lib/chess-empire-client', () => ({
  getStudentProfile: (...a: unknown[]) => getStudentProfile(...(a as [])),
  getCoachProfile: (...a: unknown[]) => getCoachProfile(...(a as [])),
  getStudentRatings: vi.fn(async () => []),
  getStudentRank: vi.fn(async () => ({
    branch_rank: null,
    school_rank: null,
    branch_size: null,
    school_size: null,
  })),
  listBranches: (...a: unknown[]) => listBranches(...(a as [])),
  listActiveStudentsByCoach: (...a: unknown[]) =>
    listActiveStudentsByCoach(...(a as [])),
}));

vi.mock('@/lib/student-name', () => ({
  resolveStudentDisplayName: () => 'Some Student',
}));

vi.mock('@/components/empire/EmpireHomePage', () => ({
  __esModule: true,
  default: (props: { state: string }) => (
    <div data-testid="empire-home" data-state={props.state} />
  ),
}));
vi.mock('@/components/empire/EmpireCoachHome', () => ({
  __esModule: true,
  default: (props: { coachDisplayName: string | null }) => (
    <div data-testid="empire-coach" data-name={props.coachDisplayName ?? ''} />
  ),
}));
vi.mock('@/components/empire/EmpireNoLinkClient', () => ({
  __esModule: true,
  default: (props: { children: React.ReactNode }) => (
    <div data-testid="nolink-poller">{props.children}</div>
  ),
}));

import { renderEmpireHomepage } from '../empire-homepage-render';

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.state = 'verified';
  memberStore.role = 'coach';
  memberStore.studentId = 'coach-uuid';
  getStudentProfile.mockClear();
  getCoachProfile.mockClear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('renderEmpireHomepage — coach path', () => {
  it('renders the coach variant with the coach name and never calls getStudentProfile', async () => {
    const ui = await renderEmpireHomepage('org-1');
    expect(ui).not.toBeNull();
    const { getByTestId, queryByTestId } = render(ui!);
    const coach = getByTestId('empire-coach');
    expect(coach.getAttribute('data-name')).toBe('Aigerim Nur');
    expect(queryByTestId('empire-home')).toBeNull();
    expect(getCoachProfile).toHaveBeenCalledWith('coach-uuid');
    expect(getStudentProfile).not.toHaveBeenCalled();
  });

  it('degrades to a name-less coach greeting if the coach profile fetch fails', async () => {
    getCoachProfile.mockRejectedValueOnce(new Error('404'));
    const ui = await renderEmpireHomepage('org-1');
    const { getByTestId } = render(ui!);
    expect(getByTestId('empire-coach').getAttribute('data-name')).toBe('');
    expect(getStudentProfile).not.toHaveBeenCalled();
  });

  it('renders the student dashboard for a verified student (role=student)', async () => {
    memberStore.role = 'student';
    memberStore.studentId = 'stu-1';
    const ui = await renderEmpireHomepage('org-1');
    const { getByTestId, queryByTestId } = render(ui!);
    expect(getByTestId('empire-home').getAttribute('data-state')).toBe('verified');
    expect(queryByTestId('empire-coach')).toBeNull();
    expect(getStudentProfile).toHaveBeenCalledWith('stu-1');
    expect(getCoachProfile).not.toHaveBeenCalled();
  });

  it('wraps the no_link state in the polling client', async () => {
    memberStore.state = 'no_link';
    memberStore.studentId = null;
    const ui = await renderEmpireHomepage('org-1');
    const { getByTestId } = render(ui!);
    expect(getByTestId('nolink-poller')).toBeTruthy();
    expect(getByTestId('empire-home').getAttribute('data-state')).toBe('no_link');
  });
});
