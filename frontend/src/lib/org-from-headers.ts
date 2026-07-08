import { cache } from 'react';
import { headers } from 'next/headers';

import { type Organization, parseOrgFromHeaders } from '@/contexts/organization-types';

// Hoisted via React `cache()` so server components and metadata routes share
// one fetch per request — keeps a 5-minute revalidate cache while avoiding
// duplicate round-trips inside a single render.
export const fetchOrgData = cache(
  async (orgId: string, orgSlug: string): Promise<Organization | null> => {
    try {
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
      const res = await fetch(
        `${backendUrl}/api/admin/organizations/by-slug/${orgSlug}`,
        { next: { revalidate: 300 }, signal: AbortSignal.timeout(3000) },
      );
      if (!res.ok) return null;
      const data = await res.json();
      return {
        id: data.id || orgId,
        slug: data.slug || orgSlug,
        name: data.name || 'Chesster',
        logoUrl: data.logo_url || null,
        logoMarkUrl: data.logo_mark_url || null,
        pwaIconUrl: data.pwa_icon_url || null,
        faviconUrl: data.favicon_url || null,
        primaryColor: data.primary_color || '#1a73e8',
        secondaryColor: data.secondary_color || '#ffffff',
        accentColor: data.accent_color || '#ffd700',
        customCss: data.custom_css || null,
        landingPageConfig: data.landing_page_config || {},
        contactEmail: data.contact_email || null,
        status: data.status || 'active',
        deletionRequestedAt: data.deletion_requested_at || null,
      };
    } catch {
      return null;
    }
  },
);

export const loadOrgFromHeaders = cache(async (): Promise<Organization | null> => {
  const headersList = await headers();
  const orgInfo = parseOrgFromHeaders(headersList);
  if (!orgInfo) return null;
  return fetchOrgData(orgInfo.orgId, orgInfo.orgSlug);
});
