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
  useLocale: () => 'en',
}));

// The auth-variant LanguageSwitcher imports the setLocale server action, which
// pulls in next/headers — stub it so the page renders in jsdom.
vi.mock('@/app/actions/setLocale', () => ({ setLocale: vi.fn() }));

vi.mock('next/image', () => ({
  __esModule: true,
  // eslint-disable-next-line @next/next/no-img-element
  default: (props: Record<string, unknown>) => <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />,
}));

const routerReplace = vi.fn();
const searchState: { invite: string | null } = { invite: null };
const pathState: { pathname: string } = { pathname: '/sign-up' };
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
  useSearchParams: () => ({ get: (k: string) => (k === 'invite' ? searchState.invite : null) }),
  usePathname: () => pathState.pathname,
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

/** An invite JWT whose exp is `secondsAgo` in the past by this device's clock. */
function inviteJwtExpiredAgo(secondsAgo: number): string {
  const exp = Math.floor(Date.now() / 1000) - secondsAgo;
  return `${b64url({ alg: 'HS256' })}.${b64url({ exp, first_name: 'Saken' })}.sig`;
}

beforeEach(() => {
  cleanup();
  routerReplace.mockReset();
  searchState.invite = null;
  pathState.pathname = '/sign-up';
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

  it('white-label + no invite + nothing stored → redirects to the branch picker (/register)', async () => {
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';

    render(<SignUpPage />);

    await waitFor(() => expect(routerReplace).toHaveBeenCalledWith('/register'));
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

  it('renders the auth-variant language switcher button', () => {
    orgState.isWhiteLabel = false;

    render(<SignUpPage />);

    const btn = screen.getByRole('button', { name: 'Change language' });
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain('EN');
  });

  it('white-label + Clerk sub-step + dropped invite query → proceeds (the bug)', async () => {
    // Clerk navigates to the OTP step and drops `?invite=`. The guard must not
    // fire here, or the in-progress registration is killed.
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    pathState.pathname = '/sign-up/verify-email-address';
    searchState.invite = null;

    render(<SignUpPage />);

    expect(screen.getByTestId('clerk-signup')).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('white-label + no invite query but valid invite in storage → proceeds', async () => {
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    searchState.invite = null;
    sessionStorage.setItem(CE_INVITE_JWT_STORAGE_KEY, validInviteJwt());

    render(<SignUpPage />);

    await waitFor(() =>
      expect(screen.getByTestId('clerk-signup')).toBeTruthy(),
    );
    expect(routerReplace).not.toHaveBeenCalled();
  });

  it('white-label + fresh invite in the link, device clock hours fast → proceeds', async () => {
    // A 60-min invite issued seconds ago looks 2h expired on a device whose
    // clock is 3h ahead. The server re-verifies exp, so the page must not
    // bounce on the device's clock alone.
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    searchState.invite = inviteJwtExpiredAgo(2 * 3600);

    render(<SignUpPage />);

    expect(screen.getByTestId('clerk-signup')).toBeTruthy();
    expect(routerReplace).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(sessionStorage.getItem(CE_INVITE_JWT_STORAGE_KEY)).toBe(
        searchState.invite,
      ),
    );
  });

  it('white-label + invite in the link expired days ago → redirects', async () => {
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    sessionStorage.setItem(CE_WELCOME_URL_STORAGE_KEY, '/welcome/tok-abc');
    searchState.invite = inviteJwtExpiredAgo(2 * 24 * 3600);

    render(<SignUpPage />);

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith('/welcome/tok-abc'),
    );
    expect(screen.queryByTestId('clerk-signup')).toBeNull();
  });

  it('white-label + no invite query, stored invite expired hours ago → still redirects', async () => {
    // The grace is for a link that just arrived; a copy left in storage from an
    // earlier visit is checked strictly so a returning user gets a fresh invite.
    orgState.isWhiteLabel = true;
    orgState.slug = 'chess-empire';
    sessionStorage.setItem(CE_WELCOME_URL_STORAGE_KEY, '/welcome/tok-abc');
    localStorage.setItem(CE_INVITE_JWT_STORAGE_KEY, inviteJwtExpiredAgo(2 * 3600));

    render(<SignUpPage />);

    await waitFor(() =>
      expect(routerReplace).toHaveBeenCalledWith('/welcome/tok-abc'),
    );
    expect(screen.queryByTestId('clerk-signup')).toBeNull();
  });
});
