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
}

export interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  token: string;
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
    .select(
      'id, user_id, role, joined_at, email, name, external_student_id, external_source, link_status, link_verified_at, link_revoked_at, organization_id',
    )
    .eq('organization_id', orgId)
    .eq('external_source', 'chess_empire')
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
    .select(
      'id, user_id, role, joined_at, email, name, external_student_id, external_source, link_status, link_verified_at, link_revoked_at, organization_id',
    )
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
    .select(
      'id, user_id, role, joined_at, email, name, external_student_id, external_source, link_status, link_verified_at, link_revoked_at, organization_id',
    )
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
