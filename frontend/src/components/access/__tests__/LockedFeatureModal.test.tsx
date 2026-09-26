/**
 * @vitest-environment jsdom
 *
 * Behavior tests for the locked-feature upsell modal, both reasons:
 *   - frozen → "continue on your own" CTA to /upgrade/continue + contact school
 *   - expired → "keep going" CTA to /upgrade/expired, no contact-school line
 *   - dismissible via close button, backdrop, and Esc
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string, vars?: Record<string, string>) =>
    vars ? `${k}:${Object.values(vars).join(',')}` : k,
}));
vi.mock('next/link', () => ({
  __esModule: true,
  default: ({
    href,
    children,
    onClick,
  }: {
    href: string;
    children: React.ReactNode;
    onClick?: () => void;
  }) => (
    <a href={href} onClick={onClick}>
      {children}
    </a>
  ),
}));

import LockedFeatureModal from '../LockedFeatureModal';

afterEach(cleanup);

describe('LockedFeatureModal', () => {
  it('frozen: names the feature, links to the frozen upgrade path, shows contact school', () => {
    const onClose = vi.fn();
    const { container } = render(
      <LockedFeatureModal
        featureKey="puzzles"
        reason="frozen"
        upgradePath="/upgrade/continue"
        onClose={onClose}
      />,
    );
    // Title interpolates the feature name.
    expect(screen.getByText('lockedTitle:feature.puzzles')).toBeTruthy();
    expect(screen.getByText('frozenBody')).toBeTruthy();
    const cta = container.querySelector('a[href="/upgrade/continue"]');
    expect(cta).toBeTruthy();
    expect(cta?.textContent).toBe('continueCta');
    expect(screen.getByText('contactSchool')).toBeTruthy();
  });

  it('expired: keep-going CTA to the expired path, no contact-school line', () => {
    const { container } = render(
      <LockedFeatureModal
        featureKey="play"
        reason="expired"
        upgradePath="/upgrade/expired"
        onClose={vi.fn()}
      />,
    );
    const cta = container.querySelector('a[href="/upgrade/expired"]');
    expect(cta?.textContent).toBe('keepGoingCta');
    expect(screen.queryByText('contactSchool')).toBeNull();
  });

  it('closes on backdrop click and Escape', () => {
    const onClose = vi.fn();
    render(
      <LockedFeatureModal
        featureKey="coach"
        reason="frozen"
        upgradePath="/upgrade/continue"
        onClose={onClose}
      />,
    );
    fireEvent.click(screen.getByTestId('locked-feature-modal'));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
