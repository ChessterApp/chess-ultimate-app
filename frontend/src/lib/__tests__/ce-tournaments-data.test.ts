/**
 * Tests for `loadCETournamentSnapshot` — the shared server-side tournaments
 * snapshot. Focus on the family (multi-member) additions from Phase 2:
 *   - a single verified link keeps the legacy shape byte-compatible;
 *   - a family account exposes `members[]` + per-card `registrations[]` while
 *     still populating the primary `studentName` / `registration_id` fields;
 *   - a per-member fetch failure degrades that member gracefully.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

const authStore: { userId: string | null } = { userId: 'user-1' };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => ({ userId: authStore.userId }),
}));

interface FakeMember {
  state: string;
  studentId: string | null;
  relationship: 'self' | 'child' | 'other';
}
const memberStore: { members: FakeMember[] } = { members: [] };
vi.mock('@/lib/chess-empire-member', () => ({
  getVerifiedMembersForUser: vi.fn(async () => memberStore.members),
}));

interface FakeEdge {
  studentId: string;
  orgId: string | null;
  relationship: 'child' | 'other';
  name: string | null;
}
const edgeStore: { edges: FakeEdge[] } = { edges: [] };
vi.mock('@/lib/family-link-invite', () => ({
  getFamilyLinkedStudentIds: vi.fn(async () => edgeStore.edges),
}));

// CE client: a fixed one-tournament schedule; names + registrations are
// scripted per student id so each member resolves independently.
const nameById: Record<string, string | null> = {};
const regsById: Record<
  string,
  Array<{ id: string; tournament_id: string }> | Error
> = {};
vi.mock('@/lib/chess-empire-client', () => ({
  listTournaments: vi.fn(async () => [
    {
      id: 't-1',
      name: 'Spring Open',
      info: null,
      tournament_date: '2026-03-14',
      start_time: '10:30:00',
      time_format: 'Blitz',
      registration_fee: 0,
      rounds: 7,
      capacity: 20,
      status: 'open',
      registered_count: 2,
      branch_id: 'br-1',
      branch: { id: 'br-1', name: 'Almaty Arena' },
    },
  ]),
  listBranches: vi.fn(async () => [{ id: 'br-1', name: 'Almaty Arena' }]),
  getTournamentRoster: vi.fn(async () => ['Existing One', 'Existing Two']),
  getStudentDisplayName: vi.fn(async (id: string) => {
    const v = nameById[id];
    if (v instanceof Error) throw v;
    return v ?? null;
  }),
  getStudentTournamentRegistrations: vi.fn(async (id: string) => {
    const v = regsById[id];
    if (v instanceof Error) throw v;
    return v ?? [];
  }),
}));

import { loadCETournamentSnapshot } from '../ce-tournaments-data';

beforeEach(() => {
  authStore.userId = 'user-1';
  memberStore.members = [];
  edgeStore.edges = [];
  for (const k of Object.keys(nameById)) delete nameById[k];
  for (const k of Object.keys(regsById)) delete regsById[k];
});

describe('loadCETournamentSnapshot — family snapshot', () => {
  it('logged-out viewer: no members, no registrations', async () => {
    authStore.userId = null;
    const snap = await loadCETournamentSnapshot();
    expect(snap.membership).toBe('logged_out');
    expect(snap.members).toEqual([]);
    expect(snap.studentName).toBeNull();
    expect(snap.tournaments[0].registrations).toEqual([]);
    expect(snap.tournaments[0].is_registered).toBe(false);
  });

  it('single verified link: legacy fields populated, one member entry', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
    ];
    nameById['stu-self'] = 'Aidos S';
    regsById['stu-self'] = [{ id: 'reg-1', tournament_id: 't-1' }];

    const snap = await loadCETournamentSnapshot();
    expect(snap.membership).toBe('verified');
    expect(snap.studentName).toBe('Aidos S');
    expect(snap.members).toEqual([
      { studentId: 'stu-self', name: 'Aidos S', relationship: 'self' },
    ]);
    const card = snap.tournaments[0];
    expect(card.registration_id).toBe('reg-1');
    expect(card.is_registered).toBe(true);
    expect(card.registrations).toEqual([
      { studentId: 'stu-self', registrationId: 'reg-1' },
    ]);
  });

  it('family account: members[] + per-card registrations[]; primary fields from the self row', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-child', relationship: 'child' },
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
    ];
    nameById['stu-child'] = 'Alikhan';
    nameById['stu-self'] = 'Parent P';
    // Only the child is registered for t-1; the self row is not.
    regsById['stu-child'] = [{ id: 'reg-child', tournament_id: 't-1' }];
    regsById['stu-self'] = [];

    const snap = await loadCETournamentSnapshot();
    expect(snap.membership).toBe('verified');
    // Primary = the 'self' row → its name drives the legacy studentName.
    expect(snap.studentName).toBe('Parent P');
    expect(snap.members).toEqual([
      { studentId: 'stu-child', name: 'Alikhan', relationship: 'child' },
      { studentId: 'stu-self', name: 'Parent P', relationship: 'self' },
    ]);

    const card = snap.tournaments[0];
    // The self row (primary) is NOT registered → legacy fields stay empty.
    expect(card.registration_id).toBeNull();
    expect(card.is_registered).toBe(false);
    // But the child's registration is present in the multi-member list.
    expect(card.registrations).toEqual([
      { studentId: 'stu-child', registrationId: 'reg-child' },
    ]);
  });

  it('primary registration still populates the legacy fields for a family self row', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
      { state: 'verified', studentId: 'stu-child', relationship: 'child' },
    ];
    nameById['stu-self'] = 'Parent P';
    nameById['stu-child'] = 'Alikhan';
    regsById['stu-self'] = [{ id: 'reg-self', tournament_id: 't-1' }];
    regsById['stu-child'] = [{ id: 'reg-child', tournament_id: 't-1' }];

    const snap = await loadCETournamentSnapshot();
    const card = snap.tournaments[0];
    expect(card.registration_id).toBe('reg-self');
    expect(card.is_registered).toBe(true);
    expect(card.registrations).toEqual(
      expect.arrayContaining([
        { studentId: 'stu-self', registrationId: 'reg-self' },
        { studentId: 'stu-child', registrationId: 'reg-child' },
      ]),
    );
    expect(card.registrations).toHaveLength(2);
  });

  it('unions a family-edge student into members + registrations (linchpin)', async () => {
    // Caller owns only their self row; the child is reachable ONLY through an
    // accepted family edge. Phase 3 must surface it in the picker AND resolve its
    // name + existing registrations, exactly like a row member.
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
    ];
    edgeStore.edges = [
      { studentId: 'stu-edge', orgId: 'org-1', relationship: 'child', name: 'Edge Name' },
    ];
    nameById['stu-self'] = 'Parent P';
    nameById['stu-edge'] = 'Bek Live'; // live name wins over the edge's stored name
    regsById['stu-self'] = [];
    regsById['stu-edge'] = [{ id: 'reg-edge', tournament_id: 't-1' }];

    const snap = await loadCETournamentSnapshot();
    expect(snap.membership).toBe('verified');
    expect(snap.members).toEqual([
      { studentId: 'stu-self', name: 'Parent P', relationship: 'self' },
      {
        studentId: 'stu-edge',
        name: 'Bek Live',
        relationship: 'child',
        source: 'chess_empire',
      },
    ]);
    const card = snap.tournaments[0];
    expect(card.registrations).toEqual([
      { studentId: 'stu-edge', registrationId: 'reg-edge' },
    ]);
    // The edge student is not the primary → legacy fields stay from the self row.
    expect(card.registration_id).toBeNull();
  });

  it('dedups an edge that duplicates an owned member row (member wins)', async () => {
    // The same student is both owned AND present as an edge → it must appear ONCE.
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
      { state: 'verified', studentId: 'stu-dup', relationship: 'child' },
    ];
    edgeStore.edges = [
      { studentId: 'stu-dup', orgId: 'org-1', relationship: 'other', name: 'Edge Dup' },
    ];
    nameById['stu-self'] = 'Parent P';
    nameById['stu-dup'] = 'Owned Dup';
    regsById['stu-self'] = [];
    regsById['stu-dup'] = [{ id: 'reg-dup', tournament_id: 't-1' }];

    const snap = await loadCETournamentSnapshot();
    // Exactly one entry for stu-dup, with the OWNED row's relationship ('child').
    expect(snap.members.filter((m) => m.studentId === 'stu-dup')).toEqual([
      { studentId: 'stu-dup', name: 'Owned Dup', relationship: 'child' },
    ]);
    const card = snap.tournaments[0];
    expect(
      card.registrations.filter((r) => r.studentId === 'stu-dup'),
    ).toHaveLength(1);
  });

  it('falls back to the edge stored name when the live lookup returns null', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
    ];
    edgeStore.edges = [
      { studentId: 'stu-edge', orgId: 'org-1', relationship: 'child', name: 'Stored Edge' },
    ];
    nameById['stu-self'] = 'Parent P';
    nameById['stu-edge'] = null; // live name unavailable → use the edge's name

    const snap = await loadCETournamentSnapshot();
    expect(snap.members).toEqual([
      { studentId: 'stu-self', name: 'Parent P', relationship: 'self' },
      {
        studentId: 'stu-edge',
        name: 'Stored Edge',
        relationship: 'child',
        source: 'chess_empire',
      },
    ]);
  });

  it('a per-member fetch failure degrades that member gracefully', async () => {
    memberStore.members = [
      { state: 'verified', studentId: 'stu-self', relationship: 'self' },
      { state: 'verified', studentId: 'stu-child', relationship: 'child' },
    ];
    nameById['stu-self'] = 'Parent P';
    nameById['stu-child'] = new Error('name boom') as unknown as string;
    regsById['stu-self'] = [{ id: 'reg-self', tournament_id: 't-1' }];
    regsById['stu-child'] = new Error('regs boom');

    const snap = await loadCETournamentSnapshot();
    expect(snap.membership).toBe('verified');
    // The failing child keeps a null name and contributes no registrations,
    // without sinking the snapshot or the healthy self row.
    expect(snap.members).toEqual([
      { studentId: 'stu-self', name: 'Parent P', relationship: 'self' },
      { studentId: 'stu-child', name: null, relationship: 'child' },
    ]);
    const card = snap.tournaments[0];
    expect(card.registration_id).toBe('reg-self');
    expect(card.registrations).toEqual([
      { studentId: 'stu-self', registrationId: 'reg-self' },
    ]);
  });
});
