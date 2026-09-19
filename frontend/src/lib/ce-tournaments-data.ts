/**
 * Chess Empire tournaments — shared server-side snapshot.
 *
 * Single source of truth for the CE tournament schedule + rosters + the viewer's
 * own registration status. Consumed by both the SSR view
 * (`ChessEmpireTournaments`) and the polling API route
 * (`/api/chess-empire/tournaments`) so the initial paint and every 15s refresh
 * produce byte-identical card shapes. All CE calls (and the service key) stay
 * server-side.
 *
 * The design is a faithful port of the vanilla public schedule
 * (chess-empire-database/tournaments.js): branches (excluding НИШ / Zhandosova)
 * with upcoming counts, per-tournament full-name rosters, capacity meters.
 */
import 'server-only';
import { auth } from '@clerk/nextjs/server';
import {
  getVerifiedMembersForUser,
  type MemberRelationship,
  type MemberSource,
} from '@/lib/chess-empire-member';
import { getFamilyLinkedStudentIds } from '@/lib/family-link-invite';
import {
  listTournaments,
  listBranches,
  getStudentTournamentRegistrations,
  getStudentDisplayName,
  getTournamentRoster,
} from '@/lib/chess-empire-client';

/** Branches hidden from the public schedule (mirrors the vanilla page). */
export const EXCLUDED_BRANCHES = ['НИШ', 'Zhandosova'];

export interface CETournamentCard {
  id: string;
  name: string;
  info: string | null;
  tournament_date: string;
  start_time: string | null;
  time_format: string | null;
  registration_fee: number;
  rounds: number;
  capacity: number;
  /** 'open' | 'closed' | 'cancelled'. */
  status: string;
  registered_count: number;
  branch_id: string | null;
  branch_name: string | null;
  /** ISO deadline for the flip-clock countdown, when the schedule exposes one. */
  registration_deadline: string | null;
  /** Registered players' full names, in registration order. */
  roster: string[];
  /**
   * Non-null when the PRIMARY member is already registered. Kept for byte
   * compatibility with single-link callers and the poll route; multi-member UI
   * reads `registrations` instead.
   */
  registration_id: string | null;
  is_registered: boolean;
  /**
   * Every family member registered for this tournament (studentId →
   * registrationId). Empty for a logged-out/unverified viewer. A single-link
   * account has at most one entry — mirroring `registration_id`.
   */
  registrations: CETournamentRegistration[];
}

export interface CETournamentRegistration {
  studentId: string;
  registrationId: string;
}

/** A verified family member the viewer may register/cancel. */
export interface CETournamentMember {
  studentId: string;
  name: string | null;
  relationship: MemberRelationship;
  /** Onboarding track — the tournaments view lowers the add gate for 'online'. */
  source: MemberSource;
}

export interface CEBranchRef {
  id: string;
  name: string;
}

export type CEMembership = 'logged_out' | 'unverified' | 'verified';

export interface CETournamentSnapshot {
  membership: CEMembership;
  /** Display name of the PRIMARY member (byte-compatible single-link field). */
  studentName: string | null;
  /** Every verified family member; empty unless `membership === 'verified'`. */
  members: CETournamentMember[];
  branches: CEBranchRef[];
  tournaments: CETournamentCard[];
}

export async function loadCETournamentSnapshot(): Promise<CETournamentSnapshot> {
  let rawTournaments: Awaited<ReturnType<typeof listTournaments>> = [];
  try {
    rawTournaments = await listTournaments(true);
  } catch (err) {
    console.error('[ce-tournaments] schedule fetch failed', err);
  }

  // Rosters for every upcoming tournament, in parallel. Each is best-effort —
  // a failed roster degrades to [] without sinking the whole snapshot.
  const rosterLists = await Promise.all(
    rawTournaments.map((t) => getTournamentRoster(t.id).catch(() => [])),
  );
  const rosterById = new Map<string, string[]>();
  rawTournaments.forEach((t, i) => rosterById.set(t.id, rosterLists[i] ?? []));

  // Viewer membership + every family member's registrations + display names.
  // A family account holds several verified links; each member's name and
  // registration set is fetched in parallel and best-effort (a failure degrades
  // that member to a null name / no registrations without sinking the snapshot).
  let membership: CEMembership = 'logged_out';
  let studentName: string | null = null;
  let members: CETournamentMember[] = [];
  // Per-tournament: all members registered (drives the multi-member UI).
  const registrationsByTournament = new Map<string, CETournamentRegistration[]>();
  // Per-tournament: the PRIMARY member's registration id (legacy single-link
  // fields — kept byte-compatible with the poll route + other consumers).
  const primaryRegistrationByTournament = new Map<string, string>();
  try {
    const { userId } = await auth();
    if (userId) {
      const verified = (await getVerifiedMembersForUser(userId)).filter(
        (m): m is typeof m & { studentId: string } => !!m.studentId,
      );
      // Students reached ONLY through an accepted family edge (self-registered /
      // cross-branch kids). Deduped against owned rows — a member row always wins
      // over an edge — so an edge never double-lists a student already owned. This
      // union is the whole point of the feature: without it edge-linked kids are
      // registerable by the API but invisible in the picker. Best-effort ([] on
      // failure) so it never blocks the owned members.
      const ownedIds = new Set(verified.map((m) => m.studentId));
      const familyEdges = (await getFamilyLinkedStudentIds(userId)).filter(
        (f) => f.studentId && !ownedIds.has(f.studentId),
      );

      // One unified, resolvable member list: owned rows first (so 'self' /
      // ordering wins for the primary), then edge-only students.
      const resolvable: CETournamentMember[] = [
        ...verified.map((m) => ({
          studentId: m.studentId,
          name: null as string | null,
          relationship: m.relationship,
          source: m.source,
        })),
        ...familyEdges.map((f) => ({
          studentId: f.studentId,
          name: f.name,
          relationship: f.relationship as MemberRelationship,
          // Edge students are real branch players registered via the CE API.
          source: 'chess_empire' as MemberSource,
        })),
      ];

      if (resolvable.length > 0) {
        membership = 'verified';
        // Deterministic primary — 'self' wins, else the first entry (owned rows
        // lead), matching `pickPrimaryState` in the member lib. Edge-only
        // students never take the primary slot unless nothing is owned.
        const primary =
          resolvable.find((m) => m.relationship === 'self') ?? resolvable[0];

        const [names, regLists] = await Promise.all([
          Promise.all(
            resolvable.map((m) =>
              getStudentDisplayName(m.studentId).catch(() => null),
            ),
          ),
          Promise.all(
            resolvable.map((m) =>
              getStudentTournamentRegistrations(m.studentId).catch(() => []),
            ),
          ),
        ]);

        members = resolvable.map((m, i) => ({
          studentId: m.studentId,
          // Prefer a freshly-resolved display name; fall back to the edge's
          // stored name when the live lookup returns nothing.
          name: names[i] ?? m.name,
          relationship: m.relationship,
          source: m.source,
        }));
        studentName =
          members.find((m) => m.studentId === primary.studentId)?.name ?? null;

        resolvable.forEach((m, i) => {
          for (const r of regLists[i]) {
            const list = registrationsByTournament.get(r.tournament_id) ?? [];
            list.push({ studentId: m.studentId, registrationId: r.id });
            registrationsByTournament.set(r.tournament_id, list);
            if (m.studentId === primary.studentId) {
              primaryRegistrationByTournament.set(r.tournament_id, r.id);
            }
          }
        });
      } else {
        membership = 'unverified';
      }
    }
  } catch (err) {
    console.error('[ce-tournaments] viewer resolution failed', err);
  }

  // Branch accordion. Prefer the full CE branch directory so empty branches
  // still render (with a "No tournaments" badge) like the vanilla page; fall
  // back to branches derived from the tournament rows if the directory is
  // unavailable. Excludes НИШ / Zhandosova either way.
  let branchRows: Awaited<ReturnType<typeof listBranches>> = [];
  try {
    branchRows = await listBranches();
  } catch {
    branchRows = [];
  }
  const branchMap = new Map<string, string>();
  for (const b of branchRows) {
    if (!EXCLUDED_BRANCHES.includes(b.name)) branchMap.set(b.id, b.name);
  }
  for (const t of rawTournaments) {
    if (
      t.branch &&
      !EXCLUDED_BRANCHES.includes(t.branch.name) &&
      !branchMap.has(t.branch.id)
    ) {
      branchMap.set(t.branch.id, t.branch.name);
    }
  }
  const branches: CEBranchRef[] = [...branchMap.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name));

  const tournaments: CETournamentCard[] = rawTournaments
    .filter((t) => !(t.branch && EXCLUDED_BRANCHES.includes(t.branch.name)))
    .map((t) => {
      const roster = rosterById.get(t.id) ?? [];
      return {
        id: t.id,
        name: t.name,
        info: t.info,
        tournament_date: t.tournament_date,
        start_time: t.start_time,
        time_format: t.time_format,
        registration_fee: t.registration_fee,
        rounds: t.rounds,
        capacity: t.capacity,
        status: t.status,
        // Roster is the source of truth for who's registered; fall back to the
        // list endpoint's count only when the roster fetch came back empty.
        registered_count: roster.length || t.registered_count,
        branch_id: t.branch_id,
        branch_name: t.branch?.name ?? null,
        registration_deadline:
          (t as { registration_deadline?: string | null }).registration_deadline ??
          null,
        roster,
        registration_id: primaryRegistrationByTournament.get(t.id) ?? null,
        is_registered: primaryRegistrationByTournament.has(t.id),
        registrations: registrationsByTournament.get(t.id) ?? [],
      };
    });

  return { membership, studentName, members, branches, tournaments };
}
