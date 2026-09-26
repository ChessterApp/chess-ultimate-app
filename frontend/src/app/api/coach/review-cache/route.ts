import { NextRequest, NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';
import { supabaseAdmin } from '@/lib/supabase-admin';

/**
 * Review Coach persistent cache (Layer 1 — REVIEW_COACH_PRD.md §6.4).
 *
 * The browser never touches the `review_coach_cache` table directly: both reads
 * and the write-through go through this authenticated server route, which uses
 * the service-role client. Cache keys are opaque (`prompt_version:kind:...`)
 * and built client-side by useReviewCoach.
 */

/** GET /api/coach/review-cache?key=... → { content, model } | { content: null } */
export async function GET(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  const key = request.nextUrl.searchParams.get('key');
  if (!key) {
    return NextResponse.json({ error: 'Missing key' }, { status: 400 });
  }

  const { data, error } = await supabaseAdmin
    .from('review_coach_cache')
    .select('content, model')
    .eq('cache_key', key)
    .maybeSingle();

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 502 });
  }

  return NextResponse.json({
    content: data?.content ?? null,
    model: data?.model ?? null,
  });
}

/** POST /api/coach/review-cache — write-through after a successful stream. */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  let body: {
    cache_key?: string;
    kind?: string;
    locale?: string;
    content?: string;
    model?: string | null;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
  }

  const { cache_key, kind, locale, content, model } = body;
  if (!cache_key || !content || !locale) {
    return NextResponse.json({ error: 'Missing fields' }, { status: 400 });
  }
  if (kind !== 'explain' && kind !== 'summary') {
    return NextResponse.json({ error: 'Invalid kind' }, { status: 400 });
  }

  const { error } = await supabaseAdmin
    .from('review_coach_cache')
    .upsert(
      { cache_key, kind, locale, content, model: model ?? null },
      { onConflict: 'cache_key', ignoreDuplicates: true },
    );

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 502 });
  }

  return NextResponse.json({ ok: true });
}
