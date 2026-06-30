/**
 * Chess Empire ↔ Chesster membership lookup.
 *
 * Phase 3 of the Chess Empire → Chesster onboarding arc (plan:
 * /root/.claude/plans/ancient-greeting-thimble.md). Resolves a Clerk user to
 * their linked CE `external_student_id` for the personalized homepage at
 * `chess-empire.chesster.io/`.
 *
 * Reads `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` on each call
 * so tests can patch the env without needing to re-import this module — same
 * pattern as `chess-empire-client.ts` and the Phase 1 admin route handlers.
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

interface MemberRow {
  external_student_id: string | null;
}

async function fetchLinkedStudentId({
  orgId,
  clerkUserId,
}: GetLinkedStudentIdArgs): Promise<string | null> {
  if (!orgId || !clerkUserId) return null;
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    throw new Error(
      'chess-empire-member: NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
    );
  }
  const supabase = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await supabase
    .from('organization_members')
    .select('external_student_id')
    .eq('organization_id', orgId)
    .eq('user_id', clerkUserId)
    .eq('external_source', 'chess_empire')
    .eq('link_status', 'verified')
    .limit(1)
    .maybeSingle();
  if (error) {
    throw new Error(`chess-empire-member: ${error.message}`);
  }
  const row = (data ?? null) as MemberRow | null;
  return row?.external_student_id ?? null;
}

export const getLinkedStudentId = cache(fetchLinkedStudentId);
