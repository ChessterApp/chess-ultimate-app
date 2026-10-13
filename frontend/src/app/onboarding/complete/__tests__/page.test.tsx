/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';

const replace = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace }) }));
vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({ isLoaded: true, isSignedIn: true, user: { id: 'user_p', unsafeMetadata: {} } }),
}));
const setPersonProperties = vi.fn();
vi.mock('@/lib/analytics/events', () => ({
  setPersonProperties: (...a: unknown[]) => setPersonProperties(...a),
}));

import OnboardingCompletePage from '../page';
import { PENDING_ANSWERS_KEY } from '@/lib/onboarding/pendingAnswers';

const fetchMock = vi.fn();

describe('/onboarding/complete', () => {
  beforeEach(() => {
    replace.mockReset();
    setPersonProperties.mockReset();
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    localStorage.setItem(
      PENDING_ANSWERS_KEY,
      JSON.stringify({ attribution: 'youtube', experience: 'beginner', parentConsent: true, parentConsentVersion: '2026-10-12' }),
    );
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('posts answers incl. consent, then $sets the server-derived person props', async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ skill_tier: 'beginner', starting_level: 1 }), { status: 200 }),
    );
    render(<OnboardingCompletePage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/learn'));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({
      parentConsent: true,
      parentConsentVersion: '2026-10-12',
    });
    expect(setPersonProperties).toHaveBeenCalledWith('user_p', {
      self_reported_source: 'youtube',
      starting_level: 1,
      skill_tier: 'beginner',
    });
  });

  it('still routes to /learn when the claim fails', async () => {
    fetchMock.mockResolvedValue(new Response('{}', { status: 500 }));
    render(<OnboardingCompletePage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith('/learn'));
    expect(setPersonProperties).toHaveBeenCalledWith('user_p', { self_reported_source: 'youtube' });
  });
});
