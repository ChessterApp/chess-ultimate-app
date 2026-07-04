/**
 * Server-side helpers for the user-facing "is this you?" confirmation flow
 * (`pending_confirm` → `verified` | delete). Kept separate from
 * `chess-empire-member.ts` so the client-hit read helper stays cache-friendly
 * and doesn't leak write helpers into a cached module.
 *
 * All writes go through the service-role client — the user's own Clerk JWT is
 * validated in the route handlers, then a service-role query enforces that
 * the row belongs to `clerkUserId` before flipping status.
 */
import 'server-only';
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

export class LinkNotFoundError extends Error {
  constructor(message: string = 'link_not_found') {
    super(message);
    this.name = 'LinkNotFoundError';
  }
}

export class LinkNotPendingError extends Error {
  constructor(message: string = 'link_not_pending') {
    super(message);
    this.name = 'LinkNotPendingError';
  }
}

interface PendingRow {
  id: string;
  organization_id: string;
  external_student_id: string | null;
  link_status: string | null;
  user_id: string;
}

let injectedClient: (() => SupabaseClient) | null = null;

export function __setLinkClientFactoryForTests(
  factory: (() => SupabaseClient) | null,
): void {
  injectedClient = factory;
}

function serviceClient(): SupabaseClient {
  if (injectedClient) return injectedClient();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      'chess-empire-link: NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
    );
  }
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}

async function loadPending(
  supabase: SupabaseClient,
  clerkUserId: string,
): Promise<PendingRow> {
  const { data, error } = await supabase
    .from('organization_members')
    .select('id, organization_id, external_student_id, link_status, user_id')
    .eq('user_id', clerkUserId)
    .eq('external_source', 'chess_empire')
    .eq('link_status', 'pending_confirm')
    .limit(1)
    .maybeSingle();
  if (error) throw new Error(`chess-empire-link.load: ${error.message}`);
  const row = data as PendingRow | null;
  if (!row) throw new LinkNotFoundError();
  return row;
}

export async function confirmPendingLink(
  clerkUserId: string,
  primaryEmail: string | null,
): Promise<{ orgId: string; studentId: string | null }> {
  const supabase = serviceClient();
  const row = await loadPending(supabase, clerkUserId);

  const nowIso = new Date().toISOString();
  const { error } = await supabase
    .from('organization_members')
    .update({ link_status: 'verified', link_verified_at: nowIso })
    .eq('id', row.id);
  if (error) throw new Error(`chess-empire-link.confirm: ${error.message}`);

  await supabase.from('link_attempts').insert({
    organization_id: row.organization_id,
    user_id: clerkUserId,
    email: primaryEmail,
    attempted_source: 'email_auto',
    status: 'success',
    chosen_student_id: row.external_student_id,
    error_message: 'user confirmed pending_confirm link',
  });

  return {
    orgId: row.organization_id,
    studentId: row.external_student_id,
  };
}

export async function rejectPendingLink(
  clerkUserId: string,
  primaryEmail: string | null,
): Promise<{ orgId: string }> {
  const supabase = serviceClient();
  const row = await loadPending(supabase, clerkUserId);

  const { error } = await supabase
    .from('organization_members')
    .delete()
    .eq('id', row.id);
  if (error) throw new Error(`chess-empire-link.reject: ${error.message}`);

  await supabase.from('link_attempts').insert({
    organization_id: row.organization_id,
    user_id: clerkUserId,
    email: primaryEmail,
    attempted_source: 'email_auto',
    status: 'no_match',
    candidate_student_ids: row.external_student_id
      ? [row.external_student_id]
      : null,
    error_message: 'user rejected email_auto match',
  });

  return { orgId: row.organization_id };
}
