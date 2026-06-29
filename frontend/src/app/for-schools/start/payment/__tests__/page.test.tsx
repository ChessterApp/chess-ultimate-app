/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import type { WizardPayload } from '@/components/school-onboarding/WizardState';

const ORG_ID = '00000000-0000-0000-0000-000000000001';

const pushMock = vi.fn();
const updateMock = vi.fn();
const setStepMock = vi.fn();

const wizardState: { payload: WizardPayload } = {
  payload: {
    tier: 'starter',
    billing_cycle: 'monthly',
    school_name: 'Almaty Chess',
    slug: 'almaty',
    email: 'owner@example.com',
  },
};

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/for-schools/start/payment',
}));

vi.mock('next-intl', () => ({
  useTranslations:
    () =>
    (key: string, _opts?: Record<string, unknown>) => `[${key}]`,
}));

vi.mock('@/components/school-onboarding/WizardState', () => ({
  useWizard: () => ({
    payload: wizardState.payload,
    update: updateMock,
    setStep: setStepMock,
    save: vi.fn(),
    step: 'payment',
    loaded: true,
  }),
}));

vi.mock('@/components/school-onboarding/BrandPreviewPanel', () => ({
  BrandPreviewPanel: () => <div data-testid="brand-preview" />,
}));

vi.mock('@/components/school-onboarding/SchoolOnboardingShell', () => ({
  SchoolOnboardingShell: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="shell">{children}</div>
  ),
}));

import StepPayment from '../page';

function mockFetch(impl: (url: string, init: RequestInit) => Promise<Response>) {
  global.fetch = vi.fn(impl as unknown as typeof fetch) as unknown as typeof fetch;
}

function jsonResponse(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('Payment page — promo code UI', () => {
  beforeEach(() => {
    pushMock.mockReset();
    updateMock.mockReset();
    setStepMock.mockReset();
    wizardState.payload = {
      tier: 'starter',
      billing_cycle: 'monthly',
      school_name: 'Almaty Chess',
      slug: 'almaty',
      email: 'owner@example.com',
    };
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders the promo heading, input, and Apply button', () => {
    render(<StepPayment />);
    expect(screen.getByText('[promoHeading]')).toBeTruthy();
    expect(screen.getByPlaceholderText('[promoPlaceholder]')).toBeTruthy();
    expect(screen.getByRole('button', { name: '[promoApply]' })).toBeTruthy();
  });

  it('Apply button is disabled while the input is empty', () => {
    render(<StepPayment />);
    const applyBtn = screen.getByRole('button', {
      name: '[promoApply]',
    }) as HTMLButtonElement;
    expect(applyBtn.disabled).toBe(true);

    const input = screen.getByPlaceholderText('[promoPlaceholder]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'FREE' } });
    expect(applyBtn.disabled).toBe(false);
  });

  it('entering FREE creates the org, calls redeem, and advances to /brand', async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    mockFetch(async (url, init) => {
      const body = init.body ? JSON.parse(init.body as string) : null;
      calls.push({ url, body });
      if (url === '/api/onboarding/create-org') {
        return jsonResponse(200, { organization: { id: ORG_ID } });
      }
      if (url === '/api/promo/redeem') {
        return jsonResponse(200, { ok: true, redirect: '/for-schools/start/brand' });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    render(<StepPayment />);
    const input = screen.getByPlaceholderText('[promoPlaceholder]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'FREE' } });
    fireEvent.click(screen.getByRole('button', { name: '[promoApply]' }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/for-schools/start/brand'));

    // Order matters: org first, then redeem.
    expect(calls[0].url).toBe('/api/onboarding/create-org');
    expect(calls[1].url).toBe('/api/promo/redeem');
    expect(calls[1].body).toEqual({
      code: 'FREE',
      orgId: ORG_ID,
      tier: 'starter',
      cycle: 'monthly',
    });

    // Wizard state was advanced.
    expect(updateMock).toHaveBeenCalledWith({ organization_id: ORG_ID });
    expect(updateMock).toHaveBeenCalledWith({ payment_status: 'paid' });
    expect(setStepMock).toHaveBeenCalledWith('brand');
  });

  it('skips the create-org call when organization_id already exists', async () => {
    wizardState.payload = {
      ...wizardState.payload,
      organization_id: ORG_ID,
    };
    const calls: string[] = [];
    mockFetch(async (url) => {
      calls.push(url);
      if (url === '/api/promo/redeem') {
        return jsonResponse(200, { ok: true, redirect: '/for-schools/start/brand' });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    render(<StepPayment />);
    const input = screen.getByPlaceholderText('[promoPlaceholder]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'FREE' } });
    fireEvent.click(screen.getByRole('button', { name: '[promoApply]' }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith('/for-schools/start/brand'));
    expect(calls).toEqual(['/api/promo/redeem']);
  });

  it('shows a localized error and does not redirect on bad code', async () => {
    wizardState.payload = {
      ...wizardState.payload,
      organization_id: ORG_ID,
    };
    mockFetch(async (url) => {
      if (url === '/api/promo/redeem') {
        return jsonResponse(404, { error: 'not_found' });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    render(<StepPayment />);
    const input = screen.getByPlaceholderText('[promoPlaceholder]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'BOGUS' } });
    fireEvent.click(screen.getByRole('button', { name: '[promoApply]' }));

    await waitFor(() => expect(screen.queryByText('[promoErrors.not_found]')).toBeTruthy());
    expect(pushMock).not.toHaveBeenCalled();
    expect(setStepMock).not.toHaveBeenCalled();
  });

  it('falls back to the generic error key for unknown server errors', async () => {
    wizardState.payload = {
      ...wizardState.payload,
      organization_id: ORG_ID,
    };
    mockFetch(async (url) => {
      if (url === '/api/promo/redeem') {
        return jsonResponse(500, { error: 'lookup_failed' });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    render(<StepPayment />);
    const input = screen.getByPlaceholderText('[promoPlaceholder]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'FREE' } });
    fireEvent.click(screen.getByRole('button', { name: '[promoApply]' }));

    await waitFor(() => expect(screen.queryByText('[promoErrors.generic]')).toBeTruthy());
    expect(pushMock).not.toHaveBeenCalled();
  });
});

describe('Payment page — Whop button regression', () => {
  beforeEach(() => {
    pushMock.mockReset();
    updateMock.mockReset();
    setStepMock.mockReset();
    wizardState.payload = {
      tier: 'starter',
      billing_cycle: 'monthly',
      school_name: 'Almaty Chess',
      slug: 'almaty',
      email: 'owner@example.com',
    };
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('renders the Whop pay button when unpaid', () => {
    render(<StepPayment />);
    expect(screen.getByRole('button', { name: '[payWithWhop]' })).toBeTruthy();
  });

  it('clicking Whop button creates org, calls /api/whop/org-checkout, and redirects', async () => {
    const CHECKOUT_URL = 'https://whop.example/checkout/abc';
    const calls: Array<{ url: string; body: unknown }> = [];
    mockFetch(async (url, init) => {
      const body = init.body ? JSON.parse(init.body as string) : null;
      calls.push({ url, body });
      if (url === '/api/onboarding/create-org') {
        return jsonResponse(200, { organization: { id: ORG_ID } });
      }
      if (url === '/api/whop/org-checkout') {
        return jsonResponse(200, { checkoutUrl: CHECKOUT_URL });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    const originalLocation = window.location;
    const hrefSetter = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        set href(v: string) {
          hrefSetter(v);
        },
        get href() {
          return originalLocation.href;
        },
      },
    });

    try {
      render(<StepPayment />);
      fireEvent.click(screen.getByRole('button', { name: '[payWithWhop]' }));

      await waitFor(() => expect(hrefSetter).toHaveBeenCalledWith(CHECKOUT_URL));

      expect(calls[0].url).toBe('/api/onboarding/create-org');
      expect(calls[1].url).toBe('/api/whop/org-checkout');
      expect(calls[1].body).toEqual({
        tier: 'starter',
        billing_cycle: 'monthly',
        org_id: ORG_ID,
      });
      expect(updateMock).toHaveBeenCalledWith({ organization_id: ORG_ID });
      // Whop path must NOT touch the promo-only wizard advance.
      expect(setStepMock).not.toHaveBeenCalled();
      expect(pushMock).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });

  it('skips create-org when organization_id already exists and goes straight to Whop checkout', async () => {
    wizardState.payload = {
      ...wizardState.payload,
      organization_id: ORG_ID,
    };
    const CHECKOUT_URL = 'https://whop.example/checkout/existing';
    const calls: string[] = [];
    mockFetch(async (url) => {
      calls.push(url);
      if (url === '/api/whop/org-checkout') {
        return jsonResponse(200, { checkoutUrl: CHECKOUT_URL });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    const originalLocation = window.location;
    const hrefSetter = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        set href(v: string) {
          hrefSetter(v);
        },
        get href() {
          return originalLocation.href;
        },
      },
    });

    try {
      render(<StepPayment />);
      fireEvent.click(screen.getByRole('button', { name: '[payWithWhop]' }));

      await waitFor(() => expect(hrefSetter).toHaveBeenCalledWith(CHECKOUT_URL));
      expect(calls).toEqual(['/api/whop/org-checkout']);
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });

  it('shows checkout error and does not redirect when org-checkout fails', async () => {
    wizardState.payload = {
      ...wizardState.payload,
      organization_id: ORG_ID,
    };
    mockFetch(async (url) => {
      if (url === '/api/whop/org-checkout') {
        return jsonResponse(500, { error: 'whop_down' });
      }
      return jsonResponse(404, { error: 'unexpected' });
    });

    const originalLocation = window.location;
    const hrefSetter = vi.fn();
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: {
        ...originalLocation,
        set href(v: string) {
          hrefSetter(v);
        },
        get href() {
          return originalLocation.href;
        },
      },
    });

    try {
      render(<StepPayment />);
      fireEvent.click(screen.getByRole('button', { name: '[payWithWhop]' }));

      await waitFor(() => expect(screen.queryByText('whop_down')).toBeTruthy());
      expect(hrefSetter).not.toHaveBeenCalled();
    } finally {
      Object.defineProperty(window, 'location', {
        configurable: true,
        value: originalLocation,
      });
    }
  });
});
