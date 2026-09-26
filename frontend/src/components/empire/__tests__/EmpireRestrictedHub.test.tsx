/**
 * @vitest-environment jsdom
 *
 * Behavior tests for the restricted-member home hub (frozen + expired):
 *   - shows the status, the still-open Learn link, and the audience CTA
 *   - frozen points to /upgrade/continue and shows the contact-school line
 *   - expired points to /upgrade/expired and hides the contact-school line
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string) => k,
}));
vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import EmpireRestrictedHub from '../EmpireRestrictedHub';

afterEach(cleanup);

describe('EmpireRestrictedHub', () => {
  it('frozen: paused status, learn link, continue CTA + contact school', () => {
    const { container } = render(<EmpireRestrictedHub reason="frozen" />);
    expect(screen.getByTestId('empire-home-frozen')).toBeTruthy();
    expect(screen.getByText('hub.frozenTitle')).toBeTruthy();
    // Learn stays open.
    expect(container.querySelector('a[href="/learn"]')).toBeTruthy();
    // Primary CTA → /upgrade/continue.
    expect(container.querySelector('a[href="/upgrade/continue"]')).toBeTruthy();
    expect(screen.getByText('hub.contactSchool')).toBeTruthy();
  });

  it('expired: trial-ended status, keep-going CTA, no contact-school line', () => {
    const { container } = render(<EmpireRestrictedHub reason="expired" />);
    expect(screen.getByTestId('empire-home-expired')).toBeTruthy();
    expect(screen.getByText('hub.expiredTitle')).toBeTruthy();
    expect(container.querySelector('a[href="/upgrade/expired"]')).toBeTruthy();
    expect(screen.queryByText('hub.contactSchool')).toBeNull();
  });
});
