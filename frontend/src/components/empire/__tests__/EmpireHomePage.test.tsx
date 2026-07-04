/**
 * @vitest-environment jsdom
 *
 * Tests for the three-state EmpireHomePage. Verifies the greeting sources
 * from the injected `studentDisplayName` and that no Clerk/email fallback
 * ever leaks in when the name is null.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string, values?: Record<string, unknown>) => {
    if (!values) return key;
    // Return `key({name})` so tests can assert on the interpolated name.
    return `${key}(${JSON.stringify(values)})`;
  },
}));

// Stub child components — we're only asserting the shell here.
vi.mock('../StudentCard', () => ({
  __esModule: true,
  default: () => <div data-testid="student-card" />,
}));
vi.mock('../ProgressBar', () => ({
  __esModule: true,
  default: () => <div data-testid="progress-bar" />,
}));
vi.mock('../Achievements', () => ({
  __esModule: true,
  default: () => <div data-testid="achievements" />,
}));
vi.mock('../RatingTrend', () => ({
  __esModule: true,
  default: () => <div data-testid="rating-trend" />,
}));
vi.mock('../PendingConfirmBanner', () => ({
  __esModule: true,
  default: ({ displayName }: { displayName: string }) => (
    <div data-testid="pending-banner" data-name={displayName} />
  ),
}));

import EmpireHomePage from '../EmpireHomePage';
import type { CEStudentProfile } from '@/lib/chess-empire-client';

const baseProfile: CEStudentProfile = {
  id: 'stu-vasco',
  first_name: 'Turabay',
  last_name: 'Ali',
  branch_id: 'br-1',
  status: 'active',
  date_of_birth: null,
  branch_name: 'Halyk Arena',
  coach_name: 'Aleksandr Olegovich',
};

afterEach(() => {
  cleanup();
});

describe('EmpireHomePage — verified state', () => {
  it('renders greeting with the injected studentDisplayName', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Turabay',
      profile: baseProfile,
      ratings: [],
      achievements: [],
      rank: {
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      },
    });
    const { getByTestId } = render(ui);
    const greeting = getByTestId('empire-home-greeting');
    // welcomeBackNamed({name}) interpolation
    expect(greeting.textContent).toContain('welcomeBackNamed');
    expect(greeting.textContent).toContain('Turabay');
  });

  it('renders name-less greeting when studentDisplayName is null', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: null,
      profile: baseProfile,
      ratings: [],
      achievements: [],
      rank: {
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      },
    });
    const { getByTestId } = render(ui);
    const greeting = getByTestId('empire-home-greeting');
    expect(greeting.textContent).toBe('welcomeBack');
  });

  it('never leaks profile.first_name or email as a fallback name', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: null,
      profile: {
        ...baseProfile,
        // These fields exist on profile but MUST NOT be used for greeting.
        first_name: 'ShouldNotAppear',
        last_name: 'ShouldNotAppear',
      },
      ratings: [],
      achievements: [],
      rank: {
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      },
    });
    const { getByTestId } = render(ui);
    const greeting = getByTestId('empire-home-greeting');
    // "ShouldNotAppear" belongs to StudentCard which is stubbed; the greeting
    // must render name-less.
    expect(greeting.textContent).toBe('welcomeBack');
    expect(greeting.textContent).not.toContain('ShouldNotAppear');
  });
});

describe('EmpireHomePage — pending_confirm state', () => {
  it('renders PendingConfirmBanner with the display name', async () => {
    const ui = await EmpireHomePage({
      state: 'pending_confirm',
      studentDisplayName: 'Turabay',
    });
    const { getByTestId } = render(ui);
    const banner = getByTestId('pending-banner');
    expect(banner.getAttribute('data-name')).toBe('Turabay');
  });

  it('degrades to no_link copy when studentDisplayName is null', async () => {
    const ui = await EmpireHomePage({
      state: 'pending_confirm',
      studentDisplayName: null,
    });
    const { queryByTestId } = render(ui);
    // Never render pending banner without a real name.
    expect(queryByTestId('pending-banner')).toBeNull();
    expect(queryByTestId('empire-home-nolink')).toBeTruthy();
  });
});

describe('EmpireHomePage — no_link state', () => {
  it('renders the name-less "getting your profile ready" copy', async () => {
    const ui = await EmpireHomePage({
      state: 'no_link',
      studentDisplayName: null,
    });
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-home-nolink')).toBeTruthy();
    expect(queryByTestId('student-card')).toBeNull();
    expect(queryByTestId('pending-banner')).toBeNull();
  });
});
