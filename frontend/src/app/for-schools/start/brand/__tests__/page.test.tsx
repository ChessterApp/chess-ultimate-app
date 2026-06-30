/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, waitFor } from '@testing-library/react';

import type { WizardPayload } from '@/components/school-onboarding/WizardState';

const ORG_ID = '00000000-0000-0000-0000-000000000001';

const wizardState: { payload: WizardPayload } = {
  payload: {
    organization_id: ORG_ID,
    primary_color: '#5e1b2c',
    secondary_color: '#ffffff',
    accent_color: '#c2a37f',
    favicon_url: 'https://x/fav.ico',
    custom_css: '',
    logo_url: 'https://x/logo.png',
  },
};

const updateMock = vi.fn();
const setStepMock = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/for-schools/start/brand',
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, _opts?: Record<string, unknown>) =>
    `[${key}]`,
}));

vi.mock('@/components/school-onboarding/WizardState', () => ({
  useWizard: () => ({
    payload: wizardState.payload,
    update: updateMock,
    setStep: setStepMock,
    save: vi.fn(),
    step: 'brand',
    loaded: true,
  }),
}));

vi.mock('@/components/school-onboarding/BrandPreviewPanel', () => ({
  BrandPreviewPanel: () => <div data-testid="brand-preview" />,
}));

vi.mock('@/components/school-onboarding/SchoolOnboardingShell', () => ({
  SchoolOnboardingShell: ({
    children,
    onNext,
  }: {
    children: React.ReactNode;
    onNext?: () => void | Promise<void>;
  }) => (
    <div data-testid="shell">
      {children}
      <button data-testid="next-btn" onClick={() => onNext?.()}>
        next
      </button>
    </div>
  ),
}));

vi.mock('@/lib/color-extract', () => ({
  extractPaletteFromUrl: vi.fn(),
}));

vi.mock('@/lib/analytics/events', () => ({
  ANALYTICS_EVENTS: {
    SCHOOL_ONBOARDING_COLORS_AUTODETECTED: 'colors_auto',
    SCHOOL_ONBOARDING_COLORS_OVERRIDDEN: 'colors_over',
  },
  track: vi.fn(),
}));

import StepBrand from '../page';

describe('Brand page — saveBrandToOrg', () => {
  beforeEach(() => {
    updateMock.mockReset();
    setStepMock.mockReset();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('PUTs logo_url along with the color/css fields', async () => {
    const calls: Array<{ url: string; body: Record<string, unknown> }> = [];
    global.fetch = vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({
        url,
        body: init?.body ? JSON.parse(init.body as string) : {},
      });
      return new Response('{}', { status: 200 });
    }) as unknown as typeof fetch;

    const { getByTestId } = render(<StepBrand />);
    fireEvent.click(getByTestId('next-btn'));

    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].url).toBe(
      `/api/admin/organizations/${ORG_ID}/settings`,
    );
    expect(calls[0].body.logo_url).toBe('https://x/logo.png');
    expect(calls[0].body.primary_color).toBe('#5e1b2c');
    expect(calls[0].body.secondary_color).toBe('#ffffff');
    expect(calls[0].body.accent_color).toBe('#c2a37f');
    expect(calls[0].body.favicon_url).toBe('https://x/fav.ico');
  });

  it('sends logo_url=null when payload has no logo', async () => {
    wizardState.payload = {
      ...wizardState.payload,
      logo_url: undefined,
    };
    const calls: Array<{ body: Record<string, unknown> }> = [];
    global.fetch = vi.fn(async (_url: string, init?: RequestInit) => {
      calls.push({ body: init?.body ? JSON.parse(init.body as string) : {} });
      return new Response('{}', { status: 200 });
    }) as unknown as typeof fetch;

    const { getByTestId } = render(<StepBrand />);
    fireEvent.click(getByTestId('next-btn'));

    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].body.logo_url).toBe(null);
  });
});
