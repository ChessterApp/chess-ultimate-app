export interface Organization {
  id: string;
  slug: string;
  name: string;
  logoUrl: string | null;
  faviconUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  customCss: string | null;
  landingPageConfig: Record<string, unknown>;
  contactEmail: string | null;
  status: string;
  deletionRequestedAt: string | null;
}

export function parseOrgFromHeaders(headers: Headers): { orgId: string; orgSlug: string } | null {
  const orgId = headers.get('x-org-id');
  const orgSlug = headers.get('x-org-slug');

  if (!orgId || !orgSlug) {
    return null;
  }

  return { orgId, orgSlug };
}
