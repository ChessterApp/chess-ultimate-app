/**
 * @vitest-environment jsdom
 *
 * Behavior tests for the frozen-membership notice:
 *   - renders the "membership paused" title, body, and contact-admin hint
 *   - has NO claim/retry affordance (frozen can't be recovered by re-claiming)
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));

import EmpireFrozenNotice from '../EmpireFrozenNotice';

afterEach(() => {
  cleanup();
});

describe('EmpireFrozenNotice', () => {
  it('renders the paused-membership copy', () => {
    render(<EmpireFrozenNotice />);
    expect(screen.getByTestId('empire-home-frozen')).toBeTruthy();
    expect(screen.getByText('frozenTitle')).toBeTruthy();
    expect(screen.getByText('frozenBody')).toBeTruthy();
    expect(screen.getByText('frozenContact')).toBeTruthy();
  });

  it('offers no claim/retry/link affordance', () => {
    const { container } = render(<EmpireFrozenNotice />);
    // No buttons and no links — the only path forward is contacting the admin,
    // never re-claiming the invite.
    expect(container.querySelectorAll('button')).toHaveLength(0);
    expect(container.querySelectorAll('a')).toHaveLength(0);
    expect(screen.queryByTestId('empire-nolink-expired-reopen')).toBeNull();
  });
});
