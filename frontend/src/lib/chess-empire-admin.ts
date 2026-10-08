/**
 * Chess Empire admin-side service helper (Chesster Supabase, service role).
 *
 * Phase 4 of the Chess Empire → Chesster onboarding arc (plan:
 * /root/.claude/plans/ancient-greeting-thimble.md § 4). Server-only. All
 * mutations enforce that the row in question belongs to the supplied orgId
 * before writing — mismatch throws `OrgScopeError`, which the route handler
 * maps to HTTP 403.
 *
 * Env (read on each call so tests can patch without re-importing):
 *  - NEXT_PUBLIC_SUPABASE_URL
 *  - SUPABASE_SERVICE_ROLE_KEY
 */
import 'server-only';
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { randomBytes } from 'node:crypto';

export class OrgScopeError extends Error {
  constructor(message: string = 'org_scope_mismatch') {
    super(message);
    this.name = 'OrgScopeError';
  }
}

export class NotFoundError extends Error {
  constructor(message: string = 'not_found') {
    super(message);
    this.name = 'NotFoundError';
  }
}

/**
 * Thrown when an access-expiry mutation targets a non-`online` member. Trial
 * windows only apply to online signups — roster (`chess_empire`) students are
 * managed by the CE database and must not be edited here.
 */
export class NotOnlineMemberError extends Error {
  constructor(message: string = 'not_online_member') {
    super(message);
    this.name = 'NotOnlineMemberError';
  }
}

export type LinkStatus =
  | 'pending'
  | 'verified'
  | 'frozen'
  | 'revoked'
  | string;

export interface CeMemberRow {
  id: string;
  user_id: string;
  role: string;
  joined_at: string;
  email?: string | null;
  name?: string | null;
  external_student_id: string | null;
  external_source: string | null;
  link_status: LinkStatus;
  link_verified_at: string | null;
  link_revoked_at: string | null;
  organization_id: string;
  /** Absolute access expiry; NULL means never expires (online trials only). */
  access_expires_at: string | null;
}

/** Columns selected for every `organization_members` read/return in this module. */
const MEMBER_COLUMNS =
  'id, user_id, role, joined_at, email, name, external_student_id, external_source, link_status, link_verified_at, link_revoked_at, organization_id, access_expires_at';

export interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  token: string;
  kind: string | null;
  access_ttl_hours: number | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  created_by: string | null;
}

interface AdminClientFactory {
  (): SupabaseClient;
}

let injectedClientFactory: AdminClientFactory | null = null;

/**
 * Test hook — inject a Supabase admin client factory. Production code does
 * NOT call this; production reads env on each call and creates a fresh
 * client. Tests use it to inject a mock instead of mocking `createClient`
 * via vi.mock (which is also possible but more brittle when this module is
 * imported alongside chess-empire-member.ts in the same test run).
 */
export function __setAdminClientFactoryForTests(
  factory: AdminClientFactory | null,
): void {
  injectedClientFactory = factory;
}

function adminClient(): SupabaseClient {
  if (injectedClientFactory) return injectedClientFactory();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      'chess-empire-admin: NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
    );
  }
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

function newToken(): string {
  return randomBytes(32).toString('hex');
}

export async function listOrgCeMembers(orgId: string): Promise<CeMemberRow[]> {
  if (!orgId) return [];
  const supabase = adminClient();
  const { data, error } = await supabase
    .from('organization_members')
    .select(MEMBER_COLUMNS)
    .eq('organization_id', orgId)
    // Both onboarding tracks funnel through the same roster panel — online
    // trial signups render under the dedicated "Online" tab.
    .in('external_source', ['chess_empire', 'online'])
    .order('joined_at', { ascending: false });
  if (error) throw new Error(`listOrgCeMembers: ${error.message}`);
  return (data ?? []) as CeMemberRow[];
}

export async function listBranchTokens(
  orgId: string,
): Promise<BranchTokenRow[]> {
  if (!orgId) return [];
  const supabase = adminClient();
  const { data, error } = await supabase
    .from('branch_invite_tokens')
    .select('*')
    .eq('organization_id', orgId)
    .order('created_at', { ascending: true });
  if (error) throw new Error(`listBranchTokens: ${error.message}`);
  return (data ?? []) as BranchTokenRow[];
}

async function loadBranchToken(
  supabase: SupabaseClient,
  tokenId: string,
): Promise<BranchTokenRow | null> {
  const { data, error } = await supabase
    .from('branch_invite_tokens')
    .select('*')
    .eq('id', tokenId)
    .maybeSingle();
  if (error) throw new Error(`loadBranchToken: ${error.message}`);
  return (data ?? null) as BranchTokenRow | null;
}

async function loadMember(
  supabase: SupabaseClient,
  memberId: string,
): Promise<CeMemberRow | null> {
  const { data, error } = await supabase
    .from('organization_members')
    .select(MEMBER_COLUMNS)
    .eq('id', memberId)
    .maybeSingle();
  if (error) throw new Error(`loadMember: ${error.message}`);
  return (data ?? null) as CeMemberRow | null;
}

export interface RotateBranchTokenArgs {
  orgId: string;
  tokenId: string;
  actorClerkUserId: string;
}

export interface RotateBranchTokenResult {
  revoked: BranchTokenRow;
  created: BranchTokenRow;
}

export async function rotateBranchToken({
  orgId,
  tokenId,
  actorClerkUserId,
}: RotateBranchTokenArgs): Promise<RotateBranchTokenResult> {
  const supabase = adminClient();
  const existing = await loadBranchToken(supabase, tokenId);
  if (!existing) throw new NotFoundError('token_not_found');
  if (existing.organization_id !== orgId) throw new OrgScopeError();

  const now = new Date().toISOString();
  const { data: revokedData, error: revokeErr } = await supabase
    .from('branch_invite_tokens')
    .update({ revoked_at: now })
    .eq('id', existing.id)
    .select('*')
    .single();
  if (revokeErr) throw new Error(`rotateBranchToken: ${revokeErr.message}`);

  const { data: createdData, error: insertErr } = await supabase
    .from('branch_invite_tokens')
    .insert({
      organization_id: existing.organization_id,
      external_branch_id: existing.external_branch_id,
      branch_name: existing.branch_name,
      // Carry the token's class + trial window onto the replacement row, or a
      // rotated online token would silently demote to a plain branch token
      // (its purple picker card would jump into the branch list).
      kind: existing.kind,
      access_ttl_hours: existing.access_ttl_hours,
      token: newToken(),
      created_by: actorClerkUserId,
    })
    .select('*')
    .single();
  if (insertErr) throw new Error(`rotateBranchToken: ${insertErr.message}`);

  return {
    revoked: revokedData as BranchTokenRow,
    created: createdData as BranchTokenRow,
  };
}

export interface RevokeBranchTokenArgs {
  orgId: string;
  tokenId: string;
  actorClerkUserId: string;
}

export async function revokeBranchToken({
  orgId,
  tokenId,
}: RevokeBranchTokenArgs): Promise<BranchTokenRow> {
  const supabase = adminClient();
  const existing = await loadBranchToken(supabase, tokenId);
  if (!existing) throw new NotFoundError('token_not_found');
  if (existing.organization_id !== orgId) throw new OrgScopeError();

  const now = new Date().toISOString();
  const { data, error } = await supabase
    .from('branch_invite_tokens')
    .update({ revoked_at: now })
    .eq('id', existing.id)
    .select('*')
    .single();
  if (error) throw new Error(`revokeBranchToken: ${error.message}`);
  return data as BranchTokenRow;
}

export interface InsertBranchTokenArgs {
  orgId: string;
  branchId: string;
  branchName: string;
  actorClerkUserId: string;
}

export class ExistingActiveTokenError extends Error {
  constructor(message: string = 'existing_active_token') {
    super(message);
    this.name = 'ExistingActiveTokenError';
  }
}

export async function insertBranchToken({
  orgId,
  branchId,
  branchName,
  actorClerkUserId,
}: InsertBranchTokenArgs): Promise<BranchTokenRow> {
  if (!branchId || !branchName) {
    throw new Error('insertBranchToken: branchId and branchName required');
  }
  const supabase = adminClient();
  const { data: existing, error: existingErr } = await supabase
    .from('branch_invite_tokens')
    .select('id')
    .eq('organization_id', orgId)
    .eq('external_branch_id', branchId)
    .is('revoked_at', null)
    .limit(1);
  if (existingErr) throw new Error(`insertBranchToken: ${existingErr.message}`);
  if (existing && existing.length > 0) {
    throw new ExistingActiveTokenError();
  }

  const { data, error } = await supabase
    .from('branch_invite_tokens')
    .insert({
      organization_id: orgId,
      external_branch_id: branchId,
      branch_name: branchName,
      token: newToken(),
      created_by: actorClerkUserId,
    })
    .select('*')
    .single();
  if (error) throw new Error(`insertBranchToken: ${error.message}`);
  return data as BranchTokenRow;
}

export interface MemberActionArgs {
  orgId: string;
  memberId: string;
  actorClerkUserId: string;
}

async function updateMemberStatus(
  args: MemberActionArgs,
  patch: Record<string, unknown>,
): Promise<CeMemberRow> {
  const supabase = adminClient();
  const existing = await loadMember(supabase, args.memberId);
  if (!existing) throw new NotFoundError('member_not_found');
  if (existing.organization_id !== args.orgId) throw new OrgScopeError();

  const { data, error } = await supabase
    .from('organization_members')
    .update(patch)
    .eq('id', existing.id)
    .select(MEMBER_COLUMNS)
    .single();
  if (error) throw new Error(`updateMemberStatus: ${error.message}`);
  return data as CeMemberRow;
}

export async function freezeMember(args: MemberActionArgs): Promise<CeMemberRow> {
  return updateMemberStatus(args, { link_status: 'frozen' });
}

export async function unfreezeMember(
  args: MemberActionArgs,
): Promise<CeMemberRow> {
  const now = new Date().toISOString();
  return updateMemberStatus(args, {
    link_status: 'verified',
    link_verified_at: now,
    link_revoked_at: null,
  });
}

export async function revokeMember(args: MemberActionArgs): Promise<CeMemberRow> {
  const now = new Date().toISOString();
  return updateMemberStatus(args, {
    link_status: 'revoked',
    link_revoked_at: now,
  });
}

// ─── Event-driven CE freeze/thaw (single student) ─────────────────────────
// When a CE admin flips a student's status in the Chess Empire admin app we
// apply the same transition the nightly cron would — immediately, for that one
// student. This mirrors a single row of `reconcile()` in
// scripts/sync-chess-empire-members.mjs: link_status flips (reusing
// freezeMember/unfreezeMember above) AND Clerk org membership is added on thaw /
// removed on freeze (kept when the member pays for their own plan). The hourly
// cron remains the safety net if a call is missed.

/** Row shape the sync helper needs, with the org's Clerk id joined in. */
export interface CeSyncMemberRow {
  id: string;
  organization_id: string;
  user_id: string;
  link_status: LinkStatus;
  clerk_org_id: string | null;
}

/**
 * Look up the single `chess_empire` member for a CE student id, resolving the
 * owning org's `clerk_org_id`. Returns null when no such student is linked.
 */
export async function loadMemberByExternalStudentId(
  externalStudentId: string,
): Promise<CeSyncMemberRow | null> {
  if (!externalStudentId) return null;
  const supabase = adminClient();
  const { data, error } = await supabase
    .from('organization_members')
    .select('id, organization_id, user_id, link_status, organizations(clerk_org_id)')
    .eq('external_student_id', externalStudentId)
    .eq('external_source', 'chess_empire')
    .maybeSingle();
  if (error) throw new Error(`loadMemberByExternalStudentId: ${error.message}`);
  if (!data) return null;
  const row = data as {
    id: string;
    organization_id: string;
    user_id: string;
    link_status: LinkStatus;
    organizations?: { clerk_org_id?: string | null } | null;
  };
  return {
    id: row.id,
    organization_id: row.organization_id,
    user_id: row.user_id,
    link_status: row.link_status,
    clerk_org_id: row.organizations?.clerk_org_id ?? null,
  };
}

/**
 * Whether `clerkUserId` holds an active personal (self-paid) Chesster
 * subscription. Mirrors `hasActivePersonalSubscription()` in the cron: a freeze
 * keeps the member's Clerk org membership when they pay for their own plan.
 * Any error / no row → false (no override).
 */
export async function hasActivePersonalSubscription(
  clerkUserId: string,
  nowMs: number = Date.now(),
): Promise<boolean> {
  if (!clerkUserId) return false;
  const supabase = adminClient();
  const { data, error } = await supabase
    .from('subscriptions')
    .select('status, current_period_end')
    .eq('clerk_user_id', clerkUserId)
    .order('updated_at', { ascending: false })
    .limit(1);
  if (error || !data || data.length === 0) return false;
  const row = data[0] as { status: string; current_period_end: string | null };
  if (!['active', 'trialing'].includes(row.status)) return false;
  if (row.current_period_end && new Date(row.current_period_end).getTime() < nowMs) {
    return false;
  }
  return true;
}

/**
 * Clerk org-membership side effects, injected so the sync helper stays
 * Clerk-free (and offline-testable). `createMembership` must swallow
 * already-a-member, `deleteMembership` must swallow already-gone — same
 * idempotency the cron's raw REST client guarantees.
 */
export interface CeSyncClerkAdapter {
  createMembership(clerkOrgId: string, userId: string): Promise<void>;
  deleteMembership(clerkOrgId: string, userId: string): Promise<void>;
}

/**
 * Reads the authoritative CE `students.status` for a student id, injected so
 * the sync helper never trusts the caller-supplied status (the service token
 * ships in the CE admin app's client JS, so the posted body is attacker-
 * controllable) and stays offline-testable — same pattern as the Clerk adapter.
 * Returns `null` when CE has no such student.
 */
export interface CeStudentStatusReader {
  getStatus(studentId: string): Promise<string | null>;
}

export type CeSyncAction = 'freeze' | 'thaw' | 'none';

export interface SyncFreezeThawArgs {
  externalStudentId: string;
  /**
   * Status posted by the CE admin app. A HINT ONLY — never acted on. The
   * helper re-reads the authoritative value from CE via `ceReader` and acts on
   * THAT, so a forged body cannot freeze/thaw arbitrary students.
   */
  ceStatus: 'active' | 'frozen';
  clerk: CeSyncClerkAdapter;
  /** Reads the authoritative CE status (injectable so tests stay offline). */
  ceReader: CeStudentStatusReader;
  /** Injectable clock (ms source) for the personal-sub check. */
  now?: () => Date;
}

export interface SyncFreezeThawResult {
  action: CeSyncAction;
  linkStatus: LinkStatus;
  memberId: string;
}

/**
 * Apply a single CE student status change to Chesster. Thaws (CE active + link
 * frozen) or freezes (CE frozen + link verified); any other pairing is a no-op,
 * mirroring `decideAction()` in the cron for the freeze/thaw directions.
 *
 * The caller-supplied `ceStatus` is a hint only — the authoritative status is
 * re-read from CE via `ceReader` and is the value acted on. Throws
 * `NotFoundError('ce_student_not_found')` when CE has no such student and
 * `NotFoundError('student_not_found')` when the student isn't linked here.
 */
export async function syncFreezeThawByStudent({
  externalStudentId,
  ceStatus,
  clerk,
  ceReader,
  now = () => new Date(),
}: SyncFreezeThawArgs): Promise<SyncFreezeThawResult> {
  const authoritativeStatus = await ceReader.getStatus(externalStudentId);
  if (authoritativeStatus === null) {
    throw new NotFoundError('ce_student_not_found');
  }
  if (authoritativeStatus !== ceStatus) {
    // Posted status disagrees with CE — forged, stale, or a race. Log it as a
    // security/observability signal and proceed on CE's authoritative value.
    console.warn(
      '[ce-sync/freeze-thaw] posted status ignored; using CE DB',
      JSON.stringify({ externalStudentId, posted: ceStatus, authoritative: authoritativeStatus }),
    );
  }

  const row = await loadMemberByExternalStudentId(externalStudentId);
  if (!row) throw new NotFoundError('student_not_found');

  const actorClerkUserId = 'ce-sync-service';

  if (authoritativeStatus === 'active' && row.link_status === 'frozen') {
    const member = await unfreezeMember({
      orgId: row.organization_id,
      memberId: row.id,
      actorClerkUserId,
    });
    if (row.clerk_org_id) {
      await clerk.createMembership(row.clerk_org_id, row.user_id);
    }
    return { action: 'thaw', linkStatus: member.link_status, memberId: row.id };
  }

  if (authoritativeStatus === 'frozen' && row.link_status === 'verified') {
    // link_status is school-side truth and always flips; the Clerk org removal
    // is skipped when the member pays for their own Chesster plan.
    const subActive = await hasActivePersonalSubscription(
      row.user_id,
      now().getTime(),
    );
    const member = await freezeMember({
      orgId: row.organization_id,
      memberId: row.id,
      actorClerkUserId,
    });
    if (row.clerk_org_id && !subActive) {
      await clerk.deleteMembership(row.clerk_org_id, row.user_id);
    }
    return { action: 'freeze', linkStatus: member.link_status, memberId: row.id };
  }

  return { action: 'none', linkStatus: row.link_status, memberId: row.id };
}

export interface SetMemberAccessExpiryArgs {
  orgId: string;
  memberId: string;
  /** New expiry (ISO). `null` grants permanent (full) access. */
  accessExpiresAt: string | null;
  actorClerkUserId: string;
}

/**
 * Set an online trial member's `access_expires_at`. `null` upgrades to full
 * (permanent) access; a past/future ISO string moves the trial window (a
 * future value re-activates an already-expired member — expiry is evaluated
 * live on read in `chess-empire-member.ts`). Roster (`chess_empire`) members
 * are rejected with `NotOnlineMemberError` — their access is managed by CE.
 */
export async function setMemberAccessExpiry({
  orgId,
  memberId,
  accessExpiresAt,
  actorClerkUserId,
}: SetMemberAccessExpiryArgs): Promise<CeMemberRow> {
  const supabase = adminClient();
  const existing = await loadMember(supabase, memberId);
  if (!existing) throw new NotFoundError('member_not_found');
  if (existing.organization_id !== orgId) throw new OrgScopeError();
  if (existing.external_source !== 'online') throw new NotOnlineMemberError();

  const { data, error } = await supabase
    .from('organization_members')
    .update({ access_expires_at: accessExpiresAt })
    .eq('id', existing.id)
    .select(MEMBER_COLUMNS)
    .single();
  if (error) throw new Error(`setMemberAccessExpiry: ${error.message}`);

  // Audit trail — no dedicated table exists for this action, so log a
  // structured line (actor, member, old → new) for after-the-fact review.
  console.info(
    '[ce-admin] setMemberAccessExpiry',
    JSON.stringify({
      actor: actorClerkUserId,
      orgId,
      memberId,
      from: existing.access_expires_at ?? null,
      to: accessExpiresAt,
    }),
  );

  return data as CeMemberRow;
}

// ─── Phase 4 — Unlinked queue + manual link ──────────────────────────────

export interface UnlinkedUserRow {
  user_id: string;
  email: string | null;
  name: string | null;
  joined_at: string | null;
  latest_attempt: {
    status: string;
    attempted_source: string;
    created_at: string;
    error_message: string | null;
    candidate_student_ids: string[] | null;
  } | null;
}

export interface RecentAttemptRow {
  id: string;
  user_id: string | null;
  email: string | null;
  attempted_source: string;
  status: string;
  candidate_student_ids: string[] | null;
  chosen_student_id: string | null;
  error_message: string | null;
  created_at: string;
}

/**
 * Return recent link_attempts for the org along with a distilled "unlinked
 * users" list — one entry per (user_id, email) that has no verified
 * organization_members row + at least one recent attempt.
 *
 * Membership rows in `pending_confirm` are considered still unlinked from
 * the admin's POV — they need either the user confirming self-service or an
 * admin overriding via manual link.
 */
export async function listUnlinkedUsers(
  orgId: string,
  limit: number = 50,
): Promise<{ unlinked: UnlinkedUserRow[]; recentAttempts: RecentAttemptRow[] }> {
  if (!orgId) return { unlinked: [], recentAttempts: [] };
  const supabase = adminClient();

  const { data: attempts, error: attemptsErr } = await supabase
    .from('link_attempts')
    .select(
      'id, user_id, email, attempted_source, status, candidate_student_ids, chosen_student_id, error_message, created_at',
    )
    .eq('organization_id', orgId)
    .order('created_at', { ascending: false })
    .limit(limit);
  if (attemptsErr) throw new Error(`listUnlinkedUsers.attempts: ${attemptsErr.message}`);
  const recentAttempts = (attempts ?? []) as RecentAttemptRow[];

  const { data: members, error: membersErr } = await supabase
    .from('organization_members')
    .select('user_id, link_status, joined_at, external_student_id')
    .eq('organization_id', orgId)
    .eq('external_source', 'chess_empire');
  if (membersErr) throw new Error(`listUnlinkedUsers.members: ${membersErr.message}`);

  const verifiedUserIds = new Set<string>();
  const joinedAtByUser = new Map<string, string>();
  for (const m of (members ?? []) as Array<{
    user_id: string;
    link_status: string | null;
    joined_at: string | null;
    external_student_id: string | null;
  }>) {
    if (m.link_status === 'verified' && m.external_student_id) {
      verifiedUserIds.add(m.user_id);
    }
    if (m.joined_at) joinedAtByUser.set(m.user_id, m.joined_at);
  }

  const latestByUser = new Map<string, RecentAttemptRow>();
  const emailByUser = new Map<string, string>();
  for (const a of recentAttempts) {
    if (!a.user_id) continue;
    if (verifiedUserIds.has(a.user_id)) continue;
    if (!latestByUser.has(a.user_id)) {
      latestByUser.set(a.user_id, a);
    }
    if (a.email && !emailByUser.has(a.user_id)) {
      emailByUser.set(a.user_id, a.email);
    }
  }

  const unlinked: UnlinkedUserRow[] = [];
  for (const [userId, attempt] of latestByUser) {
    unlinked.push({
      user_id: userId,
      email: emailByUser.get(userId) ?? null,
      name: null,
      joined_at: joinedAtByUser.get(userId) ?? null,
      latest_attempt: {
        status: attempt.status,
        attempted_source: attempt.attempted_source,
        created_at: attempt.created_at,
        error_message: attempt.error_message,
        candidate_student_ids: attempt.candidate_student_ids,
      },
    });
  }
  unlinked.sort((a, b) => {
    const ac = a.latest_attempt?.created_at ?? '';
    const bc = b.latest_attempt?.created_at ?? '';
    return bc.localeCompare(ac);
  });

  return { unlinked, recentAttempts };
}

export interface AdminLinkArgs {
  orgId: string;
  targetUserId: string;
  studentId: string;
  actorClerkUserId: string;
  notes?: string | null;
  source?: 'admin_manual' | 'backfill';
  /** Member role written to the row. Defaults to 'student'. */
  memberType?: 'student' | 'coach';
}

/**
 * Idempotent upsert of an admin-approved CE link. Used by the admin roster
 * "Unlinked users" tab and by the Vasco-style backfill (source='backfill').
 * If a row already exists for (orgId, studentId, chess_empire) → updates
 * link_status/link_source/link_notes/link_approved_by and (if the user_id
 * changed, e.g. replacing a placeholder `invite:foo@…` row) rewrites user_id.
 * If a row exists for (orgId, targetUserId, chess_empire) but points at a
 * different student, throws — admin should revoke the wrong link first.
 */
export async function adminLinkStudent(
  args: AdminLinkArgs,
): Promise<CeMemberRow> {
  const {
    orgId,
    targetUserId,
    studentId,
    actorClerkUserId,
    notes = null,
    source = 'admin_manual',
    memberType = 'student',
  } = args;
  if (!orgId || !targetUserId || !studentId) {
    throw new Error('adminLinkStudent: orgId, targetUserId, studentId required');
  }
  const supabase = adminClient();

  // 1) Row already exists for this student in this org? Update it.
  const { data: byStudent, error: byStudentErr } = await supabase
    .from('organization_members')
    .select(MEMBER_COLUMNS)
    .eq('organization_id', orgId)
    .eq('external_source', 'chess_empire')
    .eq('external_student_id', studentId)
    .limit(1);
  if (byStudentErr) throw new Error(`adminLinkStudent.byStudent: ${byStudentErr.message}`);

  const nowIso = new Date().toISOString();
  const commonPatch: Record<string, unknown> = {
    user_id: targetUserId,
    role: memberType === 'coach' ? 'coach' : 'student',
    link_status: 'verified',
    link_source: source,
    link_approved_by: actorClerkUserId,
    link_notes: notes,
    link_verified_at: nowIso,
    link_revoked_at: null,
  };

  if (byStudent && byStudent.length > 0) {
    const existing = byStudent[0] as { id: string };
    const { data, error } = await supabase
      .from('organization_members')
      .update(commonPatch)
      .eq('id', existing.id)
      .select(
        MEMBER_COLUMNS,
      )
      .single();
    if (error) throw new Error(`adminLinkStudent.update: ${error.message}`);
    return data as CeMemberRow;
  }

  // 2) No row for the student. Does this user already have a CE row in the
  // org pointing at a different student?
  const { data: byUser, error: byUserErr } = await supabase
    .from('organization_members')
    .select('id, external_student_id')
    .eq('organization_id', orgId)
    .eq('user_id', targetUserId)
    .eq('external_source', 'chess_empire')
    .limit(1);
  if (byUserErr) throw new Error(`adminLinkStudent.byUser: ${byUserErr.message}`);
  if (byUser && byUser.length > 0) {
    const row = byUser[0] as { id: string; external_student_id: string | null };
    if (row.external_student_id && row.external_student_id !== studentId) {
      throw new Error(
        `adminLinkStudent: user already linked to a different student in this org (revoke first)`,
      );
    }
    // Same student (no-op) or null external_student_id — patch it.
    const { data, error } = await supabase
      .from('organization_members')
      .update({ ...commonPatch, external_student_id: studentId })
      .eq('id', row.id)
      .select(
        MEMBER_COLUMNS,
      )
      .single();
    if (error) throw new Error(`adminLinkStudent.updateUser: ${error.message}`);
    return data as CeMemberRow;
  }

  // 3) No row at all — insert new.
  const { data, error } = await supabase
    .from('organization_members')
    .insert({
      organization_id: orgId,
      external_student_id: studentId,
      external_source: 'chess_empire',
      joined_at: nowIso,
      ...commonPatch,
    })
    .select(MEMBER_COLUMNS)
    .single();
  if (error) throw new Error(`adminLinkStudent.insert: ${error.message}`);
  return data as CeMemberRow;
}

export async function logAdminLinkAttempt(args: {
  orgId: string;
  targetUserId: string;
  studentId: string;
  status: 'success' | 'no_match' | 'webhook_error';
  errorMessage?: string | null;
  source?: 'admin_manual' | 'backfill';
}): Promise<void> {
  const supabase = adminClient();
  await supabase.from('link_attempts').insert({
    organization_id: args.orgId,
    user_id: args.targetUserId,
    email: null,
    attempted_source: args.source ?? 'admin_manual',
    status: args.status,
    chosen_student_id: args.studentId,
    error_message: args.errorMessage ?? null,
  });
}
