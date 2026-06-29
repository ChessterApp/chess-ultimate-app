/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const pushMock = vi.fn();
const setStepMock = vi.fn();
const saveMock = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
  usePathname: () => '/for-schools/start/invite',
}));

vi.mock('next-intl', () => ({
  useTranslations:
    () =>
    (key: string, opts?: Record<string, unknown>) =>
      opts ? `[${key}:${JSON.stringify(opts)}]` : `[${key}]`,
}));

vi.mock('@/components/school-onboarding/WizardState', async () => {
  const actual =
    await vi.importActual<typeof import('../WizardState')>('../WizardState');
  return {
    ...actual,
    useWizard: () => ({
      payload: {},
      update: vi.fn(),
      setStep: setStepMock,
      save: saveMock,
      step: 'invite',
      loaded: true,
    }),
  };
});

vi.mock('@/lib/analytics/events', () => ({
  ANALYTICS_EVENTS: {
    SCHOOL_ONBOARDING_STEP_VIEWED: 'school_onboarding_step_viewed',
    SCHOOL_ONBOARDING_STEP_ADVANCED: 'school_onboarding_step_advanced',
    SCHOOL_ONBOARDING_COMPLETED: 'school_onboarding_completed',
  },
  track: vi.fn(),
}));

import { SchoolOnboardingShell } from '../SchoolOnboardingShell';

describe('<SchoolOnboardingShell /> — Finish button on invite step', () => {
  beforeEach(() => {
    pushMock.mockReset();
    setStepMock.mockReset();
    saveMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it('advances to /done and sets step="done" when Finish is clicked on the invite step', () => {
    render(
      <SchoolOnboardingShell step="invite" title="Invite students">
        <div>form</div>
      </SchoolOnboardingShell>,
    );

    // The Next/Finish button is the only enabled button in the footer with the
    // default "Continue" label produced by our mocked translator.
    fireEvent.click(screen.getByRole('button', { name: /continueDefault/ }));

    expect(setStepMock).toHaveBeenCalledWith('done');
    expect(pushMock).toHaveBeenCalledWith('/for-schools/start/done');
  });
});
