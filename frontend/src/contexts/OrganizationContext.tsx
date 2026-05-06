'use client';

import { createContext, useContext, ReactNode } from 'react';
import type { Organization } from './organization-types';

export type { Organization };

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

