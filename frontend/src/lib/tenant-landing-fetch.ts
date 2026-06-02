import type { Organization } from '@/contexts/organization-types';

// PRD §11.2 #1 — server-side fetch for the tenant landing renderer.
// Shares the same `by-slug` endpoint the root layout already uses.

export async function fetchOrgForLanding(
  orgId: string,
  orgSlug: string,
): Promise<Organization | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/admin/organizations/by-slug/${orgSlug}`, {
      next: { revalidate: 300 },
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      id: data.id || orgId,
      slug: data.slug || orgSlug,
      name: data.name || 'Chesster',
      logoUrl: data.logo_url || null,
      faviconUrl: data.favicon_url || null,
      primaryColor: data.primary_color || '#1a73e8',
      secondaryColor: data.secondary_color || '#ffffff',
      accentColor: data.accent_color || '#ffd700',
      customCss: data.custom_css || null,
      landingPageConfig: data.landing_page_config || {},
      contactEmail: data.contact_email || null,
      status: data.status || 'active',
    };
  } catch {
    return null;
  }
}
