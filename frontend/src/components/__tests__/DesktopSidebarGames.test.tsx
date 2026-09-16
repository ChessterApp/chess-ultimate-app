// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';
import React from 'react';
import DesktopSidebar from '../ui/DesktopSidebar';

vi.mock('next/navigation', () => ({
  usePathname: () => '/games',
}));

vi.mock('usehooks-ts', () => ({
  useLocalStorage: (_key: string, initial: unknown) => [initial, vi.fn()],
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
  default: (props: Record<string, unknown>) => {
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...(props as { alt?: string })} alt={(props.alt as string) || ''} />;
  },
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
}));

vi.mock('@/lib/engine/maiaSingleton', () => ({
  warmMaia: vi.fn(),
}));

afterEach(cleanup);

describe('DesktopSidebar games entry', () => {
  it('renders a Games nav item linking to /games', () => {
    const { container } = render(<DesktopSidebar />);
    const link = container.querySelector('a[href="/games"]');
    expect(link).toBeTruthy();
    expect(link?.textContent).toContain('[games]');
  });

  it('marks the Games item active on /games', () => {
    const { container } = render(<DesktopSidebar />);
    const link = container.querySelector('a[href="/games"]');
    expect(link?.className).toContain('bg-purple-50');
  });
});
