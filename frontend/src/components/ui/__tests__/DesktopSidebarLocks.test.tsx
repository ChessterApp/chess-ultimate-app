// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, cleanup, fireEvent } from '@testing-library/react';
import React from 'react';
import { getAccessPolicy } from '@/lib/access-policy';
import DesktopSidebar from '../DesktopSidebar';

vi.mock('next/navigation', () => ({ usePathname: () => '/dashboard' }));
vi.mock('usehooks-ts', () => ({
  useLocalStorage: (_k: string, initial: unknown) => [initial, vi.fn()],
}));
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => `[${key}]`,
  useLocale: () => 'en',
}));
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ isSignedIn: false }),
  UserButton: () => <div data-testid="clerk-userbutton" />,
}));
vi.mock('next/image', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />
  ),
}));
vi.mock('@/components/PrefetchLink', () => ({
  __esModule: true,
  default: ({ children, ...rest }: { children: React.ReactNode; href: string }) => (
    <a {...rest}>{children}</a>
  ),
}));
vi.mock('@/components/LanguageSwitcher', () => ({
  __esModule: true,
  default: () => <div data-testid="lang-switcher" />,
}));
vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => ({ name: 'Chesster', logoUrl: null, primaryColor: '#1a73e8' }),
  useOrganization: () => ({ org: null }),
}));
vi.mock('@/lib/engine/maiaSingleton', () => ({ warmMaia: vi.fn() }));

const membershipStore = { policy: getAccessPolicy('frozen') };
vi.mock('@/components/providers/MembershipProvider', () => ({
  useMembership: () => ({ state: null, policy: membershipStore.policy }),
}));
vi.mock('@/components/access/LockedFeatureModal', () => ({
  __esModule: true,
  default: (props: { featureKey: string }) => (
    <div data-testid="locked-modal" data-feature={props.featureKey} />
  ),
}));

afterEach(cleanup);
beforeEach(() => {
  membershipStore.policy = getAccessPolicy('frozen');
});

describe('DesktopSidebar access locks', () => {
  it('renders lock icons on gated items and keeps home/learn active when restricted', () => {
    const { container, getAllByTestId } = render(<DesktopSidebar />);
    // Locked features are buttons, not links.
    expect(container.querySelector('a[href="/play"]')).toBeNull();
    expect(container.querySelector('a[href="/coach"]')).toBeNull();
    expect(container.querySelector('a[href="/database"]')).toBeNull();
    // Home + Learn stay as real links.
    expect(container.querySelector('a[href="/dashboard"]')).toBeTruthy();
    expect(container.querySelector('a[href="/learn"]')).toBeTruthy();
    expect(container.querySelector('a[href="/settings"]')).toBeTruthy();
    // Lock badges present.
    expect(getAllByTestId('nav-lock').length).toBeGreaterThan(0);
  });

  it('opens the locked-feature modal (not navigation) when a locked item is clicked', () => {
    const { container, getByTestId, queryByTestId } = render(<DesktopSidebar />);
    expect(queryByTestId('locked-modal')).toBeNull();
    const playButton = container.querySelector(
      'button[aria-disabled="true"]',
    ) as HTMLButtonElement;
    expect(playButton).toBeTruthy();
    // The first gated nav item in order is /play.
    fireEvent.click(playButton);
    expect(getByTestId('locked-modal').getAttribute('data-feature')).toBe('play');
  });

  it('renders no locks when access is full', () => {
    membershipStore.policy = getAccessPolicy('verified');
    const { container, queryAllByTestId } = render(<DesktopSidebar />);
    expect(queryAllByTestId('nav-lock')).toHaveLength(0);
    expect(container.querySelector('a[href="/play"]')).toBeTruthy();
    expect(container.querySelector('a[href="/coach"]')).toBeTruthy();
  });
});
