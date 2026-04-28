'use client';

import { useEffect } from 'react';
import { useBranding } from '@/contexts/OrganizationContext';

/**
 * Injects CSS custom properties from organization branding config onto :root.
 * Falls back to Chesster defaults when no org context is present.
 */
export default function BrandingInjector() {
  const branding = useBranding();

  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty('--brand-primary', branding.primaryColor);
    root.style.setProperty('--brand-secondary', branding.secondaryColor);
    root.style.setProperty('--brand-accent', branding.accentColor);

    return () => {
      root.style.removeProperty('--brand-primary');
      root.style.removeProperty('--brand-secondary');
      root.style.removeProperty('--brand-accent');
    };
  }, [branding.primaryColor, branding.secondaryColor, branding.accentColor]);

  return null;
}
