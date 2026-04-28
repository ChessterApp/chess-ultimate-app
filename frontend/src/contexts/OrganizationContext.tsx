'use client';

import { createContext, useContext, ReactNode } from 'react';

export interface Organization {
  id: string;
  slug: string;
  name: string;
  logoUrl: string | null;
  faviconUrl: string | null;
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  landingPageConfig: Record<string, unknown>;
  contactEmail: string | null;
  status: string;
}

interface OrganizationContextValue {
  org: Organization | null;
  isWhiteLabel: boolean;
}

const DEFAULT_BRANDING: Organization = {
  id: '',
  slug: '',
  name: 'Chesster',
  logoUrl: null,
  faviconUrl: null,
  primaryColor: '#1a73e8',
  secondaryColor: '#ffffff',
  accentColor: '#ffd700',
  landingPageConfig: {},
  contactEmail: null,
  status: 'active',
};

const OrganizationContext = createContext<OrganizationContextValue>({
  org: null,
  isWhiteLabel: false,
});

export function useOrganization() {
  return useContext(OrganizationContext);
}

/**
 * Get effective branding (org branding or Chesster defaults).
 */
export function useBranding(): Organization {
  const { org } = useOrganization();
  return org || DEFAULT_BRANDING;
}

interface OrganizationProviderProps {
  children: ReactNode;
  org: Organization | null;
}

export function OrganizationProvider({ children, org }: OrganizationProviderProps) {
  const value: OrganizationContextValue = {
    org,
    isWhiteLabel: org !== null,
  };

  return (
    <OrganizationContext.Provider value={value}>
      {children}
    </OrganizationContext.Provider>
  );
}

/**
 * Parse org data from server-side headers into an Organization object.
 * Used by server components / layout to hydrate the context.
 */
export function parseOrgFromHeaders(headers: Headers): { orgId: string; orgSlug: string } | null {
  const orgId = headers.get('x-org-id');
  const orgSlug = headers.get('x-org-slug');

  if (!orgId || !orgSlug) {
    return null;
  }

  return { orgId, orgSlug };
}
