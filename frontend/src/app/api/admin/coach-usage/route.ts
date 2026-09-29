import { NextRequest, NextResponse } from 'next/server';
import { auth, clerkClient, currentUser } from '@clerk/nextjs/server';
import type { SupabaseClient } from '@supabase/supabase-js';
import { supabaseAdmin } from '@/lib/supabase-admin';
import {
  aggregateUsage,
  isStudentId,
  resolvePeriod,
  USAGE_PERIODS,
  type Person,
  type TokenUsageRow,
  type UsagePeriod,
  type VoiceUsageRow,
} from '@/lib/coach-usage';

export const dynamic = 'force-dynamic';
export const maxDuration = 60;

/**
 * GET /api/admin/coach-usage?period=today|7d|30d|month — the AI coach's spend
 * per student for /super-admin/usage. Platform super-admins with 2FA only (the
 * same rule as the /super-admin layout). Not under /api/super-admin: that path
 * is rewritten to the Flask backend on Vercel.
 */

const PAGE = 1000; // PostgREST's row cap per request on Supabase
const PARALLEL_PAGES = 6;
const MAX_ROWS = 200_000;

// Newest schema first; older production databases lack the later columns
// (migrations 004 surface, 005 duration/tool, 016 turn/cache).
const TOKEN_COLUMNS = [
  'id,user_id,surface,model,prompt_tokens,completion_tokens,cached_tokens,estimated_cost_usd,duration_ms,tool_name,turn_id,created_at',
  'id,user_id,surface,model,prompt_tokens,completion_tokens,estimated_cost_usd,duration_ms,tool_name,created_at',
  'id,user_id,surface,model,prompt_tokens,completion_tokens,estimated_cost_usd,created_at',
  'id,user_id,model,prompt_tokens,completion_tokens,estimated_cost_usd,created_at',
];

function jsonError(error: string, status: number) {
  return NextResponse.json({ error }, { status });
}

async function superAdminDenied(): Promise<NextResponse | null> {
  const { userId } = await auth();
  if (!userId) return jsonError('Unauthorized', 401);
  const user = await currentUser();
  const role = (user?.publicMetadata as Record<string, unknown> | null)?.platform_role;
  if (role !== 'super_admin') return jsonError('Forbidden', 403);
  if (user?.twoFactorEnabled !== true) return jsonError('2FA required', 403);
  return null;
}

function missingColumn(error: { code?: string; message?: string }): boolean {
  return error.code === '42703' || /column .* does not exist/i.test(error.message ?? '');
}

async function fetchAll<T>(
  load: (from: number, to: number, withCount: boolean) => PromiseLike<{
    data: unknown[] | null;
    error: { code?: string; message?: string } | null;
    count?: number | null;
  }>,
): Promise<{ rows: T[]; truncated: boolean }> {
  const first = await load(0, PAGE - 1, true);
  if (first.error) throw first.error;
  const rows = [...((first.data ?? []) as T[])];
  const total = first.count ?? rows.length;
  const offsets: number[] = [];
  for (let at = PAGE; at < Math.min(total, MAX_ROWS); at += PAGE) offsets.push(at);
  for (let i = 0; i < offsets.length; i += PARALLEL_PAGES) {
    const pages = await Promise.all(
      offsets.slice(i, i + PARALLEL_PAGES).map((at) => load(at, at + PAGE - 1, false)),
    );
    for (const page of pages) {
      if (page.error) throw page.error;
      rows.push(...((page.data ?? []) as T[]));
    }
  }
  return { rows, truncated: total > MAX_ROWS };
}

async function fetchTokenRows(sb: SupabaseClient, fromIso: string) {
  for (const columns of TOKEN_COLUMNS) {
    try {
      return await fetchAll<TokenUsageRow>((from, to, withCount) =>
        sb
          .from('token_usage')
          .select(columns, withCount ? { count: 'exact' } : undefined)
          .gte('created_at', fromIso)
          .order('created_at', { ascending: true })
          .order('id', { ascending: true })
          .range(from, to),
      );
    } catch (err) {
      if (!missingColumn(err as { code?: string; message?: string })) throw err;
    }
  }
  throw new Error('token_usage has none of the expected columns');
}

/** Voice minutes from the quota ledger; null when the table is not there. */
async function fetchVoiceRows(sb: SupabaseClient, fromIso: string): Promise<VoiceUsageRow[] | null> {
  try {
    const { rows } = await fetchAll<VoiceUsageRow>((from, to, withCount) =>
      sb
        .from('voice_usage')
        .select('id,user_id,seconds,last_heartbeat_at,started_at', withCount ? { count: 'exact' } : undefined)
        .gte('last_heartbeat_at', fromIso)
        .order('last_heartbeat_at', { ascending: true })
        .order('id', { ascending: true })
        .range(from, to),
    );
    return rows;
  } catch (err) {
    console.warn('[coach-usage] voice_usage unavailable:', (err as Error).message ?? err);
    return null;
  }
}

function chunks<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

/** Names and emails from Clerk, schools from organization_members. */
async function fetchPeople(sb: SupabaseClient, ids: string[]): Promise<Map<string, Person>> {
  const people = new Map<string, Person>();
  for (const id of ids) people.set(id, { name: null, email: null, schools: [] });
  if (ids.length === 0) return people;

  try {
    const clerk = await clerkClient();
    for (const batch of chunks(ids, 100)) {
      const { data } = await clerk.users.getUserList({ userId: batch, limit: 100 });
      for (const u of data) {
        const person = people.get(u.id);
        if (!person) continue;
        const name = [u.firstName, u.lastName].filter(Boolean).join(' ').trim() || u.username || null;
        const email =
          u.emailAddresses.find((e) => e.id === u.primaryEmailAddressId)?.emailAddress ??
          u.emailAddresses[0]?.emailAddress ??
          null;
        person.name = name;
        person.email = email;
      }
    }
  } catch (err) {
    console.warn('[coach-usage] Clerk lookup failed:', (err as Error).message ?? err);
  }

  try {
    const members: { user_id: string; organization_id: string; name?: string | null; email?: string | null }[] = [];
    for (const batch of chunks(ids, 150)) {
      const { data, error } = await sb
        .from('organization_members')
        .select('user_id,organization_id,name,email')
        .in('user_id', batch);
      if (error) throw error;
      members.push(...((data ?? []) as typeof members));
    }
    const orgIds = [...new Set(members.map((m) => m.organization_id).filter(Boolean))];
    const orgNames = new Map<string, string>();
    for (const batch of chunks(orgIds, 150)) {
      const { data, error } = await sb.from('organizations').select('id,name').in('id', batch);
      if (error) throw error;
      for (const o of (data ?? []) as { id: string; name: string | null }[]) {
        if (o.name) orgNames.set(o.id, o.name);
      }
    }
    for (const m of members) {
      const person = people.get(m.user_id);
      if (!person) continue;
      const school = orgNames.get(m.organization_id);
      if (school && !person.schools.includes(school)) person.schools.push(school);
      person.name ??= m.name ?? null;
      person.email ??= m.email ?? null;
    }
  } catch (err) {
    console.warn('[coach-usage] school lookup failed:', (err as Error).message ?? err);
  }
  return people;
}

export async function GET(request: NextRequest) {
  const denied = await superAdminDenied();
  if (denied) return denied;

  const raw = request.nextUrl.searchParams.get('period') ?? '7d';
  const periodName = (USAGE_PERIODS as readonly string[]).includes(raw) ? (raw as UsagePeriod) : '7d';
  const period = resolvePeriod(periodName);

  try {
    const sb = supabaseAdmin;
    const [{ rows, truncated }, voiceRows] = await Promise.all([
      fetchTokenRows(sb, period.from),
      fetchVoiceRows(sb, period.from),
    ]);
    const ids = new Set<string>();
    for (const r of rows) if (isStudentId(r.user_id)) ids.add(r.user_id);
    for (const v of voiceRows ?? []) if (isStudentId(v.user_id)) ids.add(v.user_id);
    const people = await fetchPeople(sb, [...ids]);
    return NextResponse.json(aggregateUsage(rows, voiceRows, people, period, truncated));
  } catch (err) {
    console.error('[coach-usage] failed:', err);
    return jsonError('Не удалось получить расходы из базы', 502);
  }
}
