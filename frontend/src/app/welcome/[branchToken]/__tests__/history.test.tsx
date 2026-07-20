/**
 * @vitest-environment jsdom
 *
 * WelcomeFlow URL/history sync: the confirm step is mirrored to `?step=confirm`
 * via the shared usePhaseHistory hook so the browser Back button steps confirm
 * → search instead of leaving the page, and a refresh on `?step=confirm` with
 * no in-memory selection falls back to search cleanly.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ isSignedIn: false }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${Object.values(opts).join(',')}` : key,
}));

vi.mock('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => ({ name: 'Chess Empire', logoUrl: null, primaryColor: '#9333ea' }),
  useOrganization: () => ({ org: null, isWhiteLabel: false }),
}));

import WelcomeFlow from '../WelcomeFlow';

const sampleResults = [
  { studentId: 'stu-1', firstName: 'Aiman', lastName: 'Kassymova', branchName: 'Debut', coachName: 'Anna' },
];

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

beforeEach(() => {
  window.history.replaceState(null, '', '/welcome/tok-abc');
  global.fetch = vi.fn(async () => jsonResponse({ results: sampleResults }) as unknown as Response);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderFlow() {
  return render(
    <WelcomeFlow branchToken="tok-abc" branchName="Debut" organizationId="org-1" />,
  );
}

async function selectFirstResult(container: HTMLElement, findByTestId: (id: string) => Promise<HTMLElement>) {
  const input = container.querySelector('#welcome-search') as HTMLInputElement;
  fireEvent.change(input, { target: { value: 'ai' } });
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 320));
  });
  const list = await findByTestId('welcome-search-results');
  fireEvent.click(list.querySelectorAll('button')[0]);
  await waitFor(() => expect(container.textContent).toContain('confirmTitle'));
}

describe('WelcomeFlow history sync', () => {
  it('pushes a history entry and sets ?step=confirm when a result is selected', async () => {
    const { container, findByTestId } = renderFlow();
    const before = window.history.length;
    await selectFirstResult(container, findByTestId);

    expect(window.location.search).toBe('?step=confirm');
    expect(window.history.length).toBe(before + 1);
  });

  it('returns to search on popstate (Back) out of confirm', async () => {
    const { container, findByTestId } = renderFlow();
    await selectFirstResult(container, findByTestId);

    // Browser Back to the search entry.
    act(() => {
      window.history.replaceState(null, '', '/welcome/tok-abc');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    await waitFor(() => expect(container.textContent).not.toContain('confirmTitle'));
    expect(container.querySelector('#welcome-search')).not.toBeNull();
  });

  it('the confirm Back button steps back to search', async () => {
    const { container, findByTestId } = renderFlow();
    await selectFirstResult(container, findByTestId);

    const backButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('confirmBack'),
    ) as HTMLButtonElement;
    // Stub back() so jsdom doesn't fire a stray popstate into the next test;
    // drive the browser's popstate response manually instead.
    const backSpy = vi.spyOn(window.history, 'back').mockImplementation(() => {});
    fireEvent.click(backButton);
    expect(backSpy).toHaveBeenCalled();
    act(() => {
      window.history.replaceState(null, '', '/welcome/tok-abc');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    backSpy.mockRestore();

    await waitFor(() => expect(container.textContent).not.toContain('confirmTitle'));
    expect(container.querySelector('#welcome-search')).not.toBeNull();
  });

  it('falls back to search when loaded on ?step=confirm without a selection', async () => {
    window.history.replaceState(null, '', '/welcome/tok-abc?step=confirm');
    const { container } = renderFlow();

    // No selection in memory → renders search, not a broken confirm card.
    await waitFor(() => expect(container.querySelector('#welcome-search')).not.toBeNull());
    expect(container.textContent).not.toContain('confirmTitle');
    // The URL is normalized so it no longer claims a confirm step.
    expect(window.location.search).toBe('');
  });
});
