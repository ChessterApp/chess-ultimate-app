/**
 * @vitest-environment jsdom
 *
 * Behavior tests for the restricted-member level-complete conversion screen:
 *   - frozen  → "continue on your own" CTA to /upgrade/continue
 *   - expired → "keep going" CTA to /upgrade/expired
 *   - renders the completed level, the next-level teaser, and the back link
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string, vars?: Record<string, string | number>) =>
    vars ? `${k}:${Object.values(vars).join(',')}` : k,
}));
vi.mock('next/link', () => ({
  __esModule: true,
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

import LevelCompleteConversion from '../LevelCompleteConversion';

afterEach(cleanup);

describe('LevelCompleteConversion', () => {
  it('frozen: celebrates the level, teases the next level, links to /upgrade/continue', () => {
    const { container } = render(
      <LevelCompleteConversion
        reason="frozen"
        upgradePath="/upgrade/continue"
        level={3}
        nextLevelTitle="Tactics I"
        onBackToLearn={vi.fn()}
      />,
    );
    // Title interpolates the completed level.
    expect(screen.getByText('levelComplete.title:3')).toBeTruthy();
    // Next-level teaser interpolates level+1 and the title.
    expect(screen.getByText('levelComplete.nextLevel:4,Tactics I')).toBeTruthy();
    // Frozen CTA + destination.
    const cta = container.querySelector('a[href="/upgrade/continue"]');
    expect(cta?.textContent).toBe('continueCta');
  });

  it('expired: keep-going CTA points to /upgrade/expired', () => {
    const { container } = render(
      <LevelCompleteConversion
        reason="expired"
        upgradePath="/upgrade/expired"
        level={1}
        nextLevelTitle="Openings"
        onBackToLearn={vi.fn()}
      />,
    );
    const cta = container.querySelector('a[href="/upgrade/expired"]');
    expect(cta?.textContent).toBe('keepGoingCta');
  });

  it('omits the next-level teaser when there is no next level', () => {
    render(
      <LevelCompleteConversion
        reason="frozen"
        upgradePath="/upgrade/continue"
        level={8}
        nextLevelTitle={null}
        onBackToLearn={vi.fn()}
      />,
    );
    expect(screen.queryByText(/levelComplete\.nextLevel/)).toBeNull();
  });

  it('invokes onBackToLearn from the secondary link', () => {
    const onBack = vi.fn();
    render(
      <LevelCompleteConversion
        reason="frozen"
        upgradePath="/upgrade/continue"
        level={2}
        nextLevelTitle="Endgames"
        onBackToLearn={onBack}
      />,
    );
    fireEvent.click(screen.getByText('levelComplete.backToLearn'));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});
