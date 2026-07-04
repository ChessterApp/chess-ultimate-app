/**
 * Chess Empire ↔ Chesster membership lookup.
 *
 * The apex CE homepage and `/dashboard` on the CE subdomain read from here to
 * decide what to render:
 *  - `no_link` → no `organization_members` row → name-less "we're getting your
 *    profile ready" copy.
 *  - `pending_confirm` → email auto-match found a single student; the user
 *    must confirm on the homepage before we treat it as verified.
 *  - `verified` → normal personalized surface.
 *
 * `getLinkedStudentId` is kept as a thin wrapper that returns the verified
 * student id or null, for callers that only care about the terminal state.
 *
 * Reads `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` on each call
 * so tests can patch the env without needing to re-import this module — same
 * pattern as `chess-empire-client.ts`.
 *
 * Wrapped in `react cache()` so concurrent server components inside a single
 * render (homepage tree) dedupe the lookup.
 */
import 'server-only';
import { cache } from 'react';
import { createClient } from '@supabase/supabase-js';

export interface GetLinkedStudentIdArgs {
  orgId: string;
  clerkUserId: string;
}

export type MembershipState = 'no_link' | 'pending_confirm' | 'verified';

export interface MembershipStateResult {
  state: MembershipState;
  studentId: string | null;
  memberId: string | null;
}

interface MemberRow {
  id: string;
  external_student_id: string | null;
  link_status: string | null;
}

function serviceClient() {
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    throw new Error(
      'chess-empire-member: NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
    );
  }
  return createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

async function fetchMembershipState({
  orgId,
  clerkUserId,
}: GetLinkedStudentIdArgs): Promise<MembershipStateResult> {
  const noLink: MembershipStateResult = {
    state: 'no_link',
    studentId: null,
    memberId: null,
  };
  if (!orgId || !clerkUserId) return noLink;

  const supabase = serviceClient();
  const { data, error } = await supabase
    .from('organization_members')
    .select('id, external_student_id, link_status')
    .eq('organization_id', orgId)
    .eq('user_id', clerkUserId)
    .eq('external_source', 'chess_empire')
    .limit(1)
    .maybeSingle();
  if (error) {
    throw new Error(`chess-empire-member: ${error.message}`);
  }
  const row = (data ?? null) as MemberRow | null;
  if (!row || !row.external_student_id) return noLink;

  if (row.link_status === 'verified') {
    return {
      state: 'verified',
      studentId: row.external_student_id,
      memberId: row.id,
    };
  }
  if (row.link_status === 'pending_confirm') {
    return {
      state: 'pending_confirm',
      studentId: row.external_student_id,
      memberId: row.id,
    };
  }
  return noLink;
}

async function fetchLinkedStudentId(
  args: GetLinkedStudentIdArgs,
): Promise<string | null> {
  const result = await fetchMembershipState(args);
  return result.state === 'verified' ? result.studentId : null;
}

export const getMembershipState = cache(fetchMembershipState);
export const getLinkedStudentId = cache(fetchLinkedStudentId);
