/**
 * @vitest-environment jsdom
 *
 * Integration tests for the apex Page() routing logic when the request
 * targets `chess-empire.chesster.io/`. Mocks Clerk's `auth()`, Next's
 * `headers()`, the member-lookup helper, and the CE client so we can drive
 * every branch (linked / unsigned / no linkage / other tenant) without
 * needing the real CE Supabase.
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

const authStore: { current: { userId: string | null } } = { current: { userId: null } };
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => authStore.current,
}));

const memberStore: { studentId: string | null; throws: boolean } = {
  studentId: null,
  throws: false,
};
vi.mock('@/lib/chess-empire-member', () => ({
  getLinkedStudentId: vi.fn(async () => {
    if (memberStore.throws) throw new Error('member-lookup failed');
    return memberStore.studentId;
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
  default: (props: { profile: { id: string } }) => (
    <div data-testid="empire-home" data-student={props.profile?.id || ''} />
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
  memberStore.studentId = null;
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

describe('apex Page() — Chess Empire routing', () => {
  it('renders <EmpireHomePage> for signed-in linked CE student', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };
    memberStore.studentId = 'stu-1';
    ceStore.profile = {
      id: 'stu-1',
      first_name: 'Aiman',
      last_name: 'Karim',
      branch_id: 'br-1',
      status: 'active',
      date_of_birth: '2015-01-01',
    };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId } = render(ui);
    const home = getByTestId('empire-home');
    expect(home.getAttribute('data-student')).toBe('stu-1');
  });

  it('falls back to <TenantLanding> when signed-in but no linkage', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };
    memberStore.studentId = null;
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
  });

  it('falls back to <TenantLanding> when unsigned on chess-empire', async () => {
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
  });

  it('renders <TenantLanding> for non-chess-empire org (unchanged)', async () => {
    headersStore.current = {
      'x-org-id': 'org-other',
      'x-org-slug': 'some-other-school',
    };
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
  });

  it('falls back to <TenantLanding> when CE profile fetch fails', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };
    memberStore.studentId = 'stu-1';
    ceStore.profileThrows = true;
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
  });
});
