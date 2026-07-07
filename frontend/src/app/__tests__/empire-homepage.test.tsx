/**
 * @vitest-environment jsdom
 *
 * Integration tests for the apex Page() routing logic when the request
 * targets a tenant subdomain (e.g. `chess-empire.chesster.io/`). Mocks
 * Clerk's `auth()`, Next's `headers()` and `redirect()`, the member-lookup
 * helper, and the CE client so we can drive every branch (signed-in redirect
 * / unsigned landing / other tenant) without needing the real CE Supabase.
 *
 * Since signed-in users on the tenant root now server-redirect to
 * `/dashboard` (so they get the full nav shell), the signed-in branch is
 * asserted via the mocked `redirect()`; only signed-out users reach the
 * tenant landing render path.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

// ---------- Mocks ----------

const headersStore: { current: Record<string, string> } = { current: {} };
vi.mock('next/headers', () => ({
  headers: async () => ({
    get: (name: string) => headersStore.current[name.toLowerCase()] ?? null,
  }),
}));

// Mirror Next's redirect(): throw a NEXT_REDIRECT-style error so control flow
// stops exactly like it would in production, and record the destination.
class RedirectError extends Error {
  constructor(public url: string) {
    super('NEXT_REDIRECT');
  }
}
const redirectMock = vi.fn((url: string) => {
  throw new RedirectError(url);
});
vi.mock('next/navigation', () => ({
  redirect: (url: string) => redirectMock(url),
}));

const authStore: { current: { userId: string | null }; throws: boolean } = {
  current: { userId: null },
  throws: false,
};
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => {
    if (authStore.throws) throw new Error('auth failed');
    return authStore.current;
  },
}));

const memberStore: {
  studentId: string | null;
  state: 'no_link' | 'pending_confirm' | 'verified';
  throws: boolean;
} = {
  studentId: null,
  state: 'no_link',
  throws: false,
};
vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipState: vi.fn(async () => {
    if (memberStore.throws) throw new Error('member-lookup failed');
    return {
      state: memberStore.state,
      studentId: memberStore.studentId,
      memberId: memberStore.studentId ? 'mem-x' : null,
    };
  }),
}));

const ceStore: {
  profile: unknown;
  profileThrows: boolean;
  ratings: unknown[];
  achievements: unknown[];
  rank: unknown;
} = {
  profile: null,
  profileThrows: false,
  ratings: [],
  achievements: [],
  rank: {
    branch_rank: null,
    school_rank: null,
    branch_size: null,
    school_size: null,
  },
};

vi.mock('@/lib/chess-empire-client', () => ({
  getStudentProfile: vi.fn(async () => {
    if (ceStore.profileThrows) throw new Error('profile failed');
    return ceStore.profile;
  }),
  getStudentRatings: vi.fn(async () => ceStore.ratings),
  getStudentAchievements: vi.fn(async () => ceStore.achievements),
  getStudentRank: vi.fn(async () => ceStore.rank),
}));

const fetchOrgStore: { current: unknown } = { current: null };
vi.mock('@/lib/tenant-landing-fetch', () => ({
  fetchOrgForLanding: vi.fn(async () => fetchOrgStore.current),
}));

// Stub the actual visual children so the test focuses on which top-level
// shell renders rather than re-asserting child markup.
vi.mock('@/components/empire/EmpireHomePage', () => ({
  __esModule: true,
  default: (props: {
    state: 'verified' | 'pending_confirm' | 'no_link';
    studentDisplayName: string | null;
    profile?: { id: string };
  }) => (
    <div
      data-testid="empire-home"
      data-state={props.state}
      data-student={props.profile?.id || ''}
      data-name={props.studentDisplayName ?? ''}
    />
  ),
}));

vi.mock('@/components/tenant/TenantLanding', () => ({
  TenantLanding: () => <div data-testid="tenant-landing" />,
}));

// The apex landing pulls in lots of client islands and next-intl client hooks
// — stub them all to a single sentinel so we can detect the apex branch.
vi.mock('@/components/landing/LandingPageClient', () => ({
  LandingPageRedirect: () => <span data-testid="apex-redirect" />,
}));
vi.mock('@/components/landing/AnimatedCounter', () => ({
  AnimatedCounter: () => <span />,
}));
vi.mock('@/components/landing/FeatureCard', () => ({
  FeatureCard: () => <span />,
}));
vi.mock('@/components/landing/ProductCard', () => ({
  ProductCard: () => <span />,
}));
vi.mock('@/components/landing/HeroButtons', () => ({
  HeroButtons: () => <span />,
}));
vi.mock('@/components/landing/FeatureCarousel', () => ({
  FeatureCarousel: () => <span />,
}));
vi.mock('@/components/landing/TestimonialsSection', () => ({
  TestimonialsSection: () => <span />,
}));
vi.mock('@/components/landing/FooterButtons', () => ({
  FooterButton: () => <span />,
}));
vi.mock('@/components/landing/CTAButton', () => ({
  CTAButton: () => <span />,
}));
vi.mock('@/components/landing/HeroAnimatedBackground', () => ({
  HeroAnimatedBackground: () => <span />,
}));
vi.mock('@/components/landing/SocialButtons', () => ({
  SocialButtons: () => <span />,
}));
vi.mock('@/components/landing/PrefetchLinks', () => ({
  PrefetchLinks: () => <span />,
}));
vi.mock('@/components/LanguageSwitcher', () => ({
  __esModule: true,
  default: () => <span />,
}));
vi.mock('next/image', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    // eslint-disable-next-line @next/next/no-img-element
    return <img alt={(props.alt as string) || ''} src={String(props.src ?? '')} />;
  },
}));
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'en',
}));

// ---------- Tests ----------

beforeEach(() => {
  headersStore.current = {};
  authStore.current = { userId: null };
  authStore.throws = false;
  redirectMock.mockClear();
  memberStore.studentId = null;
  memberStore.state = 'no_link';
  memberStore.throws = false;
  ceStore.profile = null;
  ceStore.profileThrows = false;
  ceStore.ratings = [];
  ceStore.achievements = [];
  ceStore.rank = {
    branch_rank: null,
    school_rank: null,
    branch_size: null,
    school_size: null,
  };
  fetchOrgStore.current = null;
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('tenant Page() — root redirect + landing routing', () => {
  it('redirects a signed-in user on chess-empire root to /dashboard', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };

    const Page = (await import('../page')).default;
    await expect(Page()).rejects.toThrow('NEXT_REDIRECT');
    expect(redirectMock).toHaveBeenCalledWith('/dashboard');
  });

  it('redirects a signed-in user on any tenant org root to /dashboard', async () => {
    headersStore.current = {
      'x-org-id': 'org-other',
      'x-org-slug': 'some-other-school',
    };
    authStore.current = { userId: 'user-9' };

    const Page = (await import('../page')).default;
    await expect(Page()).rejects.toThrow('NEXT_REDIRECT');
    expect(redirectMock).toHaveBeenCalledWith('/dashboard');
  });

  it('does not redirect when auth() throws — treats as signed-out', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.throws = true;
    fetchOrgStore.current = {
      id: 'org-ce',
      slug: 'chess-empire',
      name: 'Chess Empire',
      logoUrl: null,
      primaryColor: '#000',
      secondaryColor: '#fff',
      accentColor: '#f00',
      landingPageConfig: {},
    };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId } = render(ui);
    expect(getByTestId('tenant-landing')).toBeTruthy();
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('renders <TenantLanding> when unsigned on chess-empire', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: null };
    fetchOrgStore.current = {
      id: 'org-ce',
      slug: 'chess-empire',
      name: 'Chess Empire',
      logoUrl: null,
      primaryColor: '#000',
      secondaryColor: '#fff',
      accentColor: '#f00',
      landingPageConfig: {},
    };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('tenant-landing')).toBeTruthy();
    expect(queryByTestId('empire-home')).toBeNull();
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('renders <TenantLanding> for unsigned non-chess-empire org', async () => {
    headersStore.current = {
      'x-org-id': 'org-other',
      'x-org-slug': 'some-other-school',
    };
    authStore.current = { userId: null };
    fetchOrgStore.current = {
      id: 'org-other',
      slug: 'some-other-school',
      name: 'Other School',
      logoUrl: null,
      primaryColor: '#000',
      secondaryColor: '#fff',
      accentColor: '#f00',
      landingPageConfig: {},
    };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('tenant-landing')).toBeTruthy();
    expect(queryByTestId('empire-home')).toBeNull();
    expect(redirectMock).not.toHaveBeenCalled();
  });

  it('renders the apex homepage when no org headers are present', async () => {
    headersStore.current = {};
    authStore.current = { userId: null };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('apex-redirect')).toBeTruthy();
    expect(queryByTestId('tenant-landing')).toBeNull();
    expect(redirectMock).not.toHaveBeenCalled();
  });
});
