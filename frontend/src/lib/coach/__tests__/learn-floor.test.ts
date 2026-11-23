import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('server-only', () => ({}));
const membership = vi.fn();
const profile = vi.fn();
vi.mock('@/lib/chess-empire-member', () => ({ getMembershipStateForUser: (id: string) => membership(id), getMembershipState: vi.fn() }));
vi.mock('@/lib/chess-empire-client', () => ({ getStudentProfile: (id: string) => profile(id) }));
vi.mock('next/headers', () => ({ headers: vi.fn() }));
vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));

import { coachLearnFloor, learnFloorHeader, resetCoachLearnFloor } from '../learn-floor';
import { mintDirectPass } from '../direct-pass';

const STUDENT = { source: 'chess_empire', role: 'student', state: 'verified', studentId: 's1' };

describe("the coach's Chess Empire level (tester 20.11, item 12)", () => {
  beforeEach(() => {
    resetCoachLearnFloor();
    membership.mockReset();
    profile.mockReset();
  });

  it("is a roster student's school level, by the student whatever the address", async () => {
    membership.mockResolvedValue(STUDENT);
    profile.mockResolvedValue({ current_level: 2 });
    expect(await coachLearnFloor('user_a')).toBe(2);
    expect(membership).toHaveBeenCalledWith('user_a');
  });

  it('is kept: the school is asked once for a student', async () => {
    membership.mockResolvedValue(STUDENT);
    profile.mockResolvedValue({ current_level: 3 });
    await Promise.all([coachLearnFloor('user_a'), coachLearnFloor('user_a')]);
    await coachLearnFloor('user_a');
    expect(profile).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['an online member', { ...STUDENT, source: 'online' }],
    ['a coach', { ...STUDENT, role: 'coach' }],
    ['a frozen student', { ...STUDENT, state: 'frozen' }],
  ])('none for %s', async (_, m) => {
    membership.mockResolvedValue(m);
    profile.mockResolvedValue({ current_level: 2 });
    expect(await coachLearnFloor('user_b')).toBeUndefined();
  });

  it('none when the lookup fails — progress alone decides', async () => {
    membership.mockRejectedValue(new Error('db down'));
    expect(await coachLearnFloor('user_c')).toBeUndefined();
  });

  it('goes to Hermes as a header, and in the direct pass', () => {
    expect(learnFloorHeader(2)).toEqual({ 'x-learn-floor': '2' });
    expect(learnFloorHeader(undefined)).toEqual({});
    vi.stubEnv('COACH_DIRECT_URL', 'https://coach-api.chesster.io');
    vi.stubEnv('COACH_DIRECT_SECRET', 's');
    const body = (token: string) => JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
    expect(body(mintDirectPass('u', 'free', Date.now(), 2)!.token).floor).toBe(2);
    expect('floor' in body(mintDirectPass('u', 'free')!.token)).toBe(false);
    vi.unstubAllEnvs();
  });
});
