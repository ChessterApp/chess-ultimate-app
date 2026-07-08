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
  const org = await orgFromHost(host);
  return org?.name || null;
}

export interface BrandFromHost {
  name: string;
  slug: string;
  logoUrl: string | null;
  logoMarkUrl: string | null;
  pwaIconUrl: string | null;
  faviconUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
}

export async function orgFromHost(host: string | undefined | null): Promise<BrandFromHost | null> {
  const slug = slugFromHost(host);
  if (!slug) return null;
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(
      `${backendUrl}/api/admin/organizations/by-slug/${slug}`,
      { next: { revalidate: 300 }, signal: AbortSignal.timeout(3000) },
    );
    if (!res.ok) return null;
    const data = (await res.json()) as Record<string, unknown>;
    if (!data || typeof data !== 'object') return null;
    return {
      name: (data.name as string) || 'Chesster',
      slug: (data.slug as string) || slug,
      logoUrl: (data.logo_url as string) || null,
      logoMarkUrl: (data.logo_mark_url as string) || null,
      pwaIconUrl: (data.pwa_icon_url as string) || null,
      faviconUrl: (data.favicon_url as string) || null,
      primaryColor: (data.primary_color as string) || '#9333ea',
      secondaryColor: (data.secondary_color as string) || '#ffffff',
    };
  } catch {
    return null;
  }
}
