// Resolve the tenant brand name for a given Host header.
//
// Pages-router API routes (`/pages/api/...`) can't use `next/headers`, and the
// middleware's `x-org-slug` is set on response headers (visible to RSC, not
// to Node API request handlers). So when the Mastra chat endpoint needs to
// thread orgName into the agent's RequestContext, we derive it from the
// `Host` header here.
//
// Returns null for the apex (`chesster.io` / `www.chesster.io`) and on any
// lookup failure. Lookups use Next's fetch cache so we don't hammer the
// backend on every request.

const APEX_SUFFIX = '.chesster.io';

export function slugFromHost(host: string | undefined | null): string | null {
  if (!host) return null;
  const lower = host.split(':')[0].toLowerCase();
  if (lower === 'chesster.io' || lower === 'www.chesster.io') return null;
  if (!lower.endsWith(APEX_SUFFIX)) return null;
  const slug = lower.slice(0, -APEX_SUFFIX.length);
  if (!slug || slug.includes('.')) return null;
  return slug;
}

export async function orgNameFromHost(host: string | undefined | null): Promise<string | null> {
  const slug = slugFromHost(host);
  if (!slug) return null;
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(
      `${backendUrl}/api/admin/organizations/by-slug/${slug}`,
      { next: { revalidate: 300 }, signal: AbortSignal.timeout(3000) },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as { name?: string };
    return data.name || null;
  } catch {
    return null;
  }
}
