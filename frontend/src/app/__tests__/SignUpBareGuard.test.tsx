// @vitest-environment jsdom
/**
 * Bare-registration guard on the sign-up page.
 *
 * White-label domain without a valid invite JWT → redirect back to onboarding
 * and clear stored state; with a valid invite → proceed; main domain → proceed
 * unchanged.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import React from 'react';

vi.mock('@clerk/nextjs', () => ({
  SignUp: () => <div data-testid="clerk-signup" />,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => `[${key}]`,
}));

vi.mock('next/image', () => ({
  __esModule: true,
  // eslint-disable-next-line @next/next/no-img-element
  default: (props: Record<string, unknown>) => <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />,
}));

const routerReplace = vi.fn();
const searchState: { invite: string | null } = { invite: null };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k === 'invite' ? searchState.invite : null) }),
}));

const orgState: { isWhiteLabel: boolean; slug: string } = { isWhiteLabel: false, slug: '' };
vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => ({ name: 'Chess Empire', logoUrl: null, primaryColor: '#9333ea' }),
  useOrganization: () => ({
    org: orgState.isWhiteLabel ? { slug: orgState.slug } : null,
    isWhiteLabel: orgState.isWhiteLabel,
  }),
}));

import SignUpPage from '@/app/sign-up/[[...sign-up]]/page';
import {
  CE_INVITE_JWT_STORAGE_KEY,
  CE_WELCOME_URL_STORAGE_KEY,
} from '@/lib/invite-storage';

function b64url(obj: unknown): string {
  return Buffer.from(JSON.stringify(obj))
    .toString('base64')
    .replace(/=+$/, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

/** A sign-up-page invite JWT with a future exp (signature is never verified here). */
function validInviteJwt(): string {
  const exp = Math.floor(Date.now() / 1000) + 600;
  return `${b64url({ alg: 'HS256' })}.${b64url({ exp, first_name: 'Shokan' })}.sig`;
}

beforeEach(() => {
  cleanup();
  routerReplace.mockReset();
  searchState.invite = null;
  orgState.isWhiteLabel = false;
  orgState.slug = '';
  sessionStorage.clear();
  localStorage.clear();
});

describe('Sign-up bare-registration guard', () => {
  it('white-label + no invite → redirects to stored welcome URL and clears state', async () => {
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    sessionStorage.setItem(CE_WELCOME_URL_STORAGE_KEY, '/welcome/tok-abc');
    localStorage.setItem(CE_INVITE_JWT_STORAGE_KEY, 'stale.jwt.value');

    render(<SignUpPage />);

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith('/welcome/tok-abc'),
    );
    // The Clerk form must never render.
    expect(screen.queryByTestId('clerk-signup')).toBeNull();
    expect(screen.getByTestId('signup-blocked')).toBeTruthy();
    // Stored invite + welcome state cleared.
    expect(localStorage.getItem(CE_INVITE_JWT_STORAGE_KEY)).toBeNull();
    expect(sessionStorage.getItem(CE_WELCOME_URL_STORAGE_KEY)).toBeNull();
  });

  it('white-label + no invite + nothing stored → redirects to org welcome landing (/)', async () => {
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';

    render(<SignUpPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith('/'));
    expect(screen.queryByTestId('clerk-signup')).toBeNull();
  });

  it('white-label + valid invite → proceeds, renders the Clerk form', async () => {
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    searchState.invite = validInviteJwt();

    render(<SignUpPage />);

    expect(screen.getByTestId('clerk-signup')).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
    // 3c: the valid invite is persisted for the dashboard replay recovery.
    await waitFor(() =>
      expect(sessionStorage.getItem(CE_INVITE_JWT_STORAGE_KEY)).toBe(
        searchState.invite,
      ),
    );
  });

  it('main domain (not white-label) + no invite → proceeds unchanged', async () => {
    orgState.isWhiteLabel = false;

    render(<SignUpPage />);

    expect(screen.getByTestId('clerk-signup')).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
  });
});
