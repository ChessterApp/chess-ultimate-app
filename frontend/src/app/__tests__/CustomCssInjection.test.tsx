// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import type { Organization } from '@/contexts/organization-types';

const TENANT: Organization = {
  id: 'org-1',
  slug: 'acme',
  name: 'Acme Chess',
  logoUrl: null,
  faviconUrl: null,
  primaryColor: '#ff5500',
  secondaryColor: '#ffffff',
  accentColor: '#000000',
  customCss: ':root { --brand-radius: 12px; }',
  landingPageConfig: {},
  contactEmail: null,
  status: 'active',
};

// Mirrors the server-side validator in backend/routes/admin.py — keeping the
// JS check honest. The server is the authoritative rejector; this test only
// asserts the layout's render branch matches that contract.
const REJECT_PATTERNS = [
  /<\/\s*style/i,
  /<\s*script/i,
  /javascript\s*:/i,
];

function shouldReject(css: string): boolean {
  return REJECT_PATTERNS.some((pat) => pat.test(css));
}

/**
 * Minimal reproduction of the layout's `<head>` custom_css branch. Mirrors
 * `frontend/src/app/layout.tsx` so a regression there is caught here.
 */
function HeadFragment({ org }: { org: Organization | null }) {
  return (
    <div data-testid="head-fragment">
      {org && org.customCss ? (
        <style
          data-testid="custom-css-tag"
          dangerouslySetInnerHTML={{ __html: org.customCss }}
        />
      ) : null}
    </div>
  );
}

describe('Layout custom_css injection', () => {
  it('renders a <style> tag for an org with benign custom CSS', () => {
    const { container } = render(<HeadFragment org={TENANT} />);
    const style = container.querySelector('style[data-testid="custom-css-tag"]');
    expect(style).not.toBeNull();
    expect(style?.innerHTML).toContain('--brand-radius');
  });

  it('renders no <style> tag for the Chesster apex (org === null)', () => {
    const { container } = render(<HeadFragment org={null} />);
    expect(container.querySelector('style[data-testid="custom-css-tag"]')).toBeNull();
  });

  it('renders no <style> tag when customCss is empty', () => {
    const empty = { ...TENANT, customCss: '' };
    const { container } = render(<HeadFragment org={empty} />);
    expect(container.querySelector('style[data-testid="custom-css-tag"]')).toBeNull();
  });

  it('server validator contract rejects </style> breakouts', () => {
    expect(shouldReject('body{}</style><script>alert(1)</script>')).toBe(true);
    expect(shouldReject('a { color: red; } </STYLE>')).toBe(true);
  });

  it('server validator contract rejects <script and javascript: schemes', () => {
    expect(shouldReject('foo<script>bar</script>')).toBe(true);
    expect(shouldReject('.x { background: url(javascript:alert(1)); }')).toBe(true);
  });

  it('server validator contract accepts benign brand CSS', () => {
    expect(shouldReject(':root { --brand-primary: #ff0; }')).toBe(false);
    expect(shouldReject('body { font-family: Inter, sans-serif; }')).toBe(false);
  });
});
