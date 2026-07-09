/**
 * @vitest-environment jsdom
 *
 * Tests for the three-state EmpireHomePage. Verifies the greeting sources
 * from the injected `studentDisplayName` and that no Clerk/email fallback
 * ever leaks in when the name is null. Verified state renders the V1
 * Player Card dark-slate hero.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string, values?: Record<string, unknown>) => {
    if (!values) return key;
    return `${key}(${JSON.stringify(values)})`;
  },
}));

vi.mock('../PendingConfirmBanner', () => ({
  __esModule: true,
  default: ({ displayName }: { displayName: string }) => (
    <div data-testid="pending-banner" data-name={displayName} />
  ),
}));

import EmpireHomePage from '../EmpireHomePage';
import type { CEStudentProfile } from '@/lib/chess-empire-client';

const emptyRank = {
  branch_rank: null,
  school_rank: null,
  branch_size: null,
  school_size: null,
};

const aliProfile: CEStudentProfile = {
  id: 'stu-vasco',
  first_name: 'Ali',
  last_name: 'M.',
  branch_id: 'br-1',
  status: 'active',
  date_of_birth: null,
  branch_name: 'Gagarin Park',
  coach_name: 'Vasily Mikhaylovich',
  razryad: '3rd',
  current_rating: 856,
  current_level: 7,
  current_lesson: 94,
  total_lessons: 120,
};

afterEach(() => {
  cleanup();
});

describe('EmpireHomePage — verified state', () => {
  it('renders greeting "Welcome back, Ali" for the Vasco fixture', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [
        { date: '2026-05-01', rating: 800 },
        { date: '2026-06-01', rating: 856 },
      ],
      achievements: [],
      rank: { ...emptyRank, school_rank: 1, school_size: 85 },
    });
    const { getByTestId } = render(ui);
    const greeting = getByTestId('empire-home-greeting');
    expect(greeting.textContent).toContain('welcomeBackNamed');
    expect(greeting.textContent).toContain('Ali');
  });

  it('renders name-less greeting when studentDisplayName is null', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: null,
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    const greeting = getByTestId('empire-home-greeting');
    expect(greeting.textContent).toBe('welcomeBack');
  });

  it('never leaks profile.first_name as a fallback greeting name', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: null,
      profile: {
        ...aliProfile,
        first_name: 'ShouldNotAppearInGreeting',
        last_name: 'ShouldNotAppearInGreeting',
      },
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    const greeting = getByTestId('empire-home-greeting');
    expect(greeting.textContent).toBe('welcomeBack');
    expect(greeting.textContent).not.toContain('ShouldNotAppearInGreeting');
  });

  it('renders V1 hero, stat pills, progress, next lesson, and achievements sections', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [
        { date: '2026-04-01', rating: 700 },
        { date: '2026-05-01', rating: 800 },
        { date: '2026-06-01', rating: 856 },
      ],
      achievements: [
        { id: 'a1', name: 'Bot Slayer', earned_at: '2026-05-01' },
      ],
      rank: { branch_rank: null, school_rank: 1, branch_size: null, school_size: 85 },
    });
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-home')).toBeTruthy();
    expect(getByTestId('empire-hero')).toBeTruthy();
    const avatarInitial = getByTestId('empire-avatar');
    expect(avatarInitial.tagName).toBe('DIV');
    expect(avatarInitial.textContent).toBe('A');
    expect(getByTestId('empire-razryad-chip').textContent).toBe('3rd');
    expect(getByTestId('empire-coach-chip').textContent).toContain(
      'Vasily Mikhaylovich',
    );
    expect(getByTestId('empire-branch-chip').textContent).toContain('Gagarin Park');
    expect(getByTestId('empire-rating-value').textContent).toBe('856');
    // Hero no longer renders the delta pill or sparkline (Option 2 twin columns).
    expect(queryByTestId('empire-rating-delta')).toBeNull();
    expect(queryByTestId('empire-hero-sparkline')).toBeNull();
    // League column falls back to getLeague(856) = "C" when current_league is unset.
    expect(getByTestId('empire-league-value').textContent).toContain('C');
    expect(getByTestId('empire-school-rank').textContent).toBe('#1');
    expect(getByTestId('empire-progress-level').textContent).toBe('7');
    expect(getByTestId('empire-progress-current').textContent).toBe('94');
    expect(getByTestId('empire-progress-bar')).toBeTruthy();
    expect(getByTestId('empire-trend-chart')).toBeTruthy();
    expect(getByTestId('empire-next-lesson')).toBeTruthy();
    expect(getByTestId('empire-achievements-grid')).toBeTruthy();
    expect(getByTestId('empire-continue-cta')).toBeTruthy();
    expect(queryByTestId('empire-trend-empty')).toBeNull();
  });

  it('renders the CE photo_url as the hero avatar when present', async () => {
    const photoUrl =
      'https://papgcizhfkngubwofjuo.supabase.co/storage/v1/object/public/student-photos/students/stu-vasco_1766294728627.jpg';
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, photo_url: photoUrl },
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    const avatar = getByTestId('empire-avatar');
    expect(avatar.tagName).toBe('IMG');
    expect(avatar.getAttribute('src')).toBe(photoUrl);
    expect(avatar.getAttribute('alt')).toBe('Ali');
  });

  it('falls back to the initial when profile.photo_url is null', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, photo_url: null },
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    const avatar = getByTestId('empire-avatar');
    expect(avatar.tagName).toBe('DIV');
    expect(avatar.textContent).toBe('A');
  });

  it('uses the dark-slate palette in the hero (no Chesster purple/blue)', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    const hero = getByTestId('empire-hero');
    const cls = hero.className;
    expect(cls).toContain('from-slate-900');
    expect(cls).toContain('to-slate-700');
    expect(cls).not.toMatch(/purple|indigo|blue/);
  });

  it('shows an empty rating-trend state when there is no history', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-trend-empty')).toBeTruthy();
    expect(queryByTestId('empire-trend-chart')).toBeNull();
  });

  it('renders 8 level segments with the current segment highlighted', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, current_level: 4, current_lesson: 47, total_lessons: 120 },
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    for (let i = 1; i <= 8; i++) {
      expect(getByTestId(`empire-progress-segment-${i}`)).toBeTruthy();
    }
    expect(getByTestId('empire-progress-segment-current')).toBeTruthy();
    const seg4 = getByTestId('empire-progress-segment-4');
    expect(seg4.querySelector('[data-testid="empire-progress-segment-current"]')).toBeTruthy();
    expect(seg4.getAttribute('title')).toContain('"level":4');
  });

  it('derives current level from current_lesson when profile.current_level is missing', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, current_level: undefined, current_lesson: 47, total_lessons: 120 },
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    const seg4 = getByTestId('empire-progress-segment-4');
    expect(seg4.querySelector('[data-testid="empire-progress-segment-current"]')).toBeTruthy();
  });

  it('renders live Survivor and Bot Slayer card subtitles when data is present', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
      bestSurvivalScore: 62,
      bestDefeatedBot: { name: 'Titan', rating: 2100 },
    });
    const { getByTestId } = render(ui);
    expect(getByTestId('empire-card-survivor-value').textContent).toBe('62');
    expect(getByTestId('empire-card-bot-slayer-value').textContent).toBe(
      'Titan · 2100',
    );
  });

  it('renders "—" in both cards when there is no survival/bot data', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
      bestSurvivalScore: null,
      bestDefeatedBot: null,
    });
    const { getByTestId } = render(ui);
    expect(getByTestId('empire-card-survivor-value').textContent).toBe('—');
    expect(getByTestId('empire-card-bot-slayer-value').textContent).toBe('—');
  });

  it('defaults the highlight cards to "—" when props are omitted', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    expect(getByTestId('empire-card-survivor-value').textContent).toBe('—');
    expect(getByTestId('empire-card-bot-slayer-value').textContent).toBe('—');
  });

  it('renders an achievements empty state when the list is empty', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: aliProfile,
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-achievements-empty')).toBeTruthy();
    expect(queryByTestId('empire-achievements-grid')).toBeNull();
  });
});

describe('EmpireHomePage — hero league column', () => {
  it('renders the league letter from profile.current_league', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, current_league: 'A' },
      ratings: [{ date: '2026-06-01', rating: 856 }],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    // current_league wins over the getLeague(856) = "C" fallback.
    expect(getByTestId('empire-league-value').textContent).toBe('A');
  });

  it('falls back to getLeague(rating) when current_league is null', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, current_league: null },
      ratings: [{ date: '2026-06-01', rating: 1500 }],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    // 1500 → League B.
    expect(getByTestId('empire-league-value').textContent).toBe('B');
  });

  it('shows "—" when both current_league and rating are missing', async () => {
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile: { ...aliProfile, current_league: null, current_rating: null },
      ratings: [],
      achievements: [],
      rank: emptyRank,
    });
    const { getByTestId } = render(ui);
    expect(getByTestId('empire-league-value').textContent).toBe('—');
  });
});

describe('EmpireHomePage — pending_confirm state', () => {
  it('renders PendingConfirmBanner with the display name', async () => {
    const ui = await EmpireHomePage({
      state: 'pending_confirm',
      studentDisplayName: 'Ali',
    });
    const { getByTestId } = render(ui);
    const banner = getByTestId('pending-banner');
    expect(banner.getAttribute('data-name')).toBe('Ali');
  });

  it('degrades to no_link copy when studentDisplayName is null', async () => {
    const ui = await EmpireHomePage({
      state: 'pending_confirm',
      studentDisplayName: null,
    });
    const { queryByTestId } = render(ui);
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
    expect(queryByTestId('empire-hero')).toBeNull();
    expect(queryByTestId('pending-banner')).toBeNull();
  });
});
