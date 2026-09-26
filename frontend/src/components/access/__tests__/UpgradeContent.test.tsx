/**
 * @vitest-environment jsdom
 *
 * Render + checkout tests for the shared upgrade page body and plan picker:
 *   - expired audience shows the trial headline, no contact-school block
 *   - continue audience shows the paused headline + contact-school block
 *   - subscribing POSTs the selected plan to /api/whop/checkout and redirects
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';

// Whop plan ids are read at module load — stub them before importing PlanPicker.
vi.hoisted(() => {
  process.env.NEXT_PUBLIC_WHOP_WEEKLY_PLAN = 'plan_week';
  process.env.NEXT_PUBLIC_WHOP_MONTHLY_PLAN = 'plan_month';
  process.env.NEXT_PUBLIC_WHOP_YEARLY_PLAN = 'plan_year';
});

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string) => k,
}));

import UpgradeContent from '../UpgradeContent';

afterEach(cleanup);

describe('UpgradeContent', () => {
  it('expired audience: trial headline, no contact-school block', () => {
    render(<UpgradeContent audience="expired" />);
    expect(screen.getByText('upgrade.expiredHeadline')).toBeTruthy();
    expect(screen.queryByText('upgrade.contactSchoolTitle')).toBeNull();
  });

  it('continue audience: paused headline + contact-school block', () => {
    render(<UpgradeContent audience="continue" />);
    expect(screen.getByText('upgrade.continueHeadline')).toBeTruthy();
    expect(screen.getByText('upgrade.contactSchoolTitle')).toBeTruthy();
  });
});

describe('PlanPicker checkout', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'location', {
      value: { href: '' },
      writable: true,
    });
  });

  it('POSTs the selected (default yearly) plan and redirects to the checkout url', async () => {
    const fetchMock = vi.fn(async () => ({
      json: async () => ({ checkoutUrl: 'https://whop.com/checkout/plan_year' }),
    }));
    vi.stubGlobal('fetch', fetchMock);

    render(<UpgradeContent audience="expired" />);
    // Yearly is selected by default → dominant CTA reads startYearly.
    fireEvent.click(screen.getByText('upgrade.startYearly'));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/whop/checkout',
        expect.objectContaining({ method: 'POST' }),
      );
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body);
    expect(body.planId).toBe('plan_year');
    await waitFor(() => {
      expect(window.location.href).toBe('https://whop.com/checkout/plan_year');
    });
    vi.unstubAllGlobals();
  });
});
