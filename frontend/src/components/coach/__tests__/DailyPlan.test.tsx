/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import type { DailyPlan as Plan } from '@/lib/coach/tool-summary';

vi.mock('@/hooks/useGeminiLive', () => ({
  __esModule: true,
  default: () => ({
    status: 'idle', isSupported: false, isActive: false, error: null, prepare: vi.fn(), connect: vi.fn(),
    prefetch: vi.fn(), disconnect: vi.fn(), sendBoardUpdate: vi.fn(), remainingSeconds: null,
  }),
}));

import DailyPlan, { DailyPlanSkeleton } from '../DailyPlan';
import CoachChat from '../CoachChat';

const coach = en.coach;
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const FULL: Plan = {
  kind: 'daily_plan',
  cards: [
    { type: 'review_last_game', game_id: 'g1', title: 'Student – Bot', moments_count: 3 },
    { type: 'weak_spot', puzzles: 5, theme: 'endgame', stat: { games_with: 4, games: 10 } },
    { type: 'opening_lesson', eco: 'C50', name: 'Italian Game' },
    { type: 'play_coach' },
  ],
};
const MINIMAL: Plan = { kind: 'daily_plan', cards: [{ type: 'weak_spot', puzzles: 5 }, { type: 'play_coach' }] };

function renderPlan(props: Partial<React.ComponentProps<typeof DailyPlan>> = {}, messages: object = en, locale = 'en') {
  const onAction = vi.fn();
  render(
    <NextIntlClientProvider locale={locale} messages={messages as Record<string, unknown>}>
      <DailyPlan plan={FULL} variant="thread" onAction={onAction} {...props} />
    </NextIntlClientProvider>,
  );
  return onAction;
}

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('DailyPlan', () => {
  it('full plan: greeting, the review first, the weak spot with its real count, two tiles', () => {
    const onAction = renderPlan({ greetingName: 'Alex' });
    expect(screen.getByText('Hi, Alex!')).toBeTruthy();
    const review = screen.getByTestId('plan-review_last_game');
    expect(review.textContent).toContain(coach.planReviewTitle);
    expect(review.textContent).toContain('3 key moments · Student – Bot');
    expect(screen.getByTestId('plan-weak_spot').textContent).toContain('Weak spot: the endgame');
    expect(screen.getByTestId('plan-weak_spot').textContent).toContain('Mistakes in 4 of 10 reviewed games');
    expect(screen.getByTestId('plan-opening_lesson').textContent).toContain('Italian Game');
    expect(screen.getByText(coach.planOrAsk)).toBeTruthy();

    fireEvent.click(review);
    expect(onAction).toHaveBeenLastCalledWith({ kind: 'send', text: coach.planReviewPrompt, reviewGameId: 'g1' });
    fireEvent.click(screen.getByTestId('plan-weak_spot'));
    expect(onAction).toHaveBeenLastCalledWith({ kind: 'send', text: 'Give me a puzzle on the endgame' });
    fireEvent.click(screen.getByTestId('plan-opening_lesson'));
    expect(onAction).toHaveBeenLastCalledWith({ kind: 'send', text: 'Teach me this opening: Italian Game (C50)' });
    fireEvent.click(screen.getByTestId('plan-play_coach'));
    expect(onAction).toHaveBeenLastCalledWith({ kind: 'play' });
  });

  it('minimal plan: puzzles on any theme lead, no made-up numbers', () => {
    renderPlan({ plan: MINIMAL });
    expect(screen.getByText(coach.planGreetingAnon)).toBeTruthy();
    const spot = screen.getByTestId('plan-weak_spot');
    expect(spot.textContent).toContain(coach.planSpotAnyTitle);
    expect(spot.textContent).toContain('5 puzzles');
    expect(spot.textContent).not.toMatch(/Mistakes/);
    expect(screen.queryByTestId('plan-review_last_game')).toBeNull();
  });

  it('a review without an engine count shows no count', () => {
    renderPlan({ plan: { kind: 'daily_plan', cards: [{ type: 'review_last_game', game_id: 'g', title: 'A – B' }] } });
    expect(screen.getByTestId('plan-review_last_game').textContent).not.toMatch(/moment/);
  });

  it('peek: the main card, the rest as chips', () => {
    const onAction = renderPlan({ variant: 'peek' });
    expect(screen.getByTestId('plan-review_last_game')).toBeTruthy();
    expect(screen.getByTestId('plan-chip-weak_spot').textContent).toBe('Puzzles: the endgame');
    fireEvent.click(screen.getByTestId('plan-chip-play_coach'));
    expect(onAction).toHaveBeenLastCalledWith({ kind: 'play' });
  });

  it('renders in Russian, plurals included', () => {
    renderPlan({ greetingName: 'Алекс' }, ru, 'ru');
    expect(screen.getByText('Привет, Алекс!')).toBeTruthy();
    expect(screen.getByTestId('plan-review_last_game').textContent).toContain('3 ключевых момента');
    expect(screen.getByTestId('plan-weak_spot').textContent).toContain('Слабое место: эндшпиль');
  });

  it('skeleton announces itself', () => {
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <DailyPlanSkeleton variant="thread" />
      </NextIntlClientProvider>,
    );
    expect(screen.getByRole('status', { name: coach.planLoading })).toBeTruthy();
  });
});

describe('CoachChat — daily-plan home', () => {
  function fetchWith(plan: unknown, planOk = true) {
    return vi.fn(async (url: string, _init?: RequestInit) => {
      if (String(url) === '/api/coach/daily-plan') return { ok: planOk, json: async () => plan };
      if (String(url) === '/api/coach/chat') {
        return { ok: true, body: new ReadableStream({ start: (c) => c.close() }) };
      }
      return { ok: true, json: async () => ({ messages: [] }) };
    });
  }

  function renderChat(props: Partial<React.ComponentProps<typeof CoachChat>> = {}) {
    return render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <CoachChat currentFen={START} sessionId="s-1" onBoardActions={() => {}} {...props} />
      </NextIntlClientProvider>,
    );
  }

  it('replaces the starter prompts; «review my last game» sends the game id', async () => {
    const fetchMock = fetchWith(FULL);
    vi.stubGlobal('fetch', fetchMock);
    renderChat({ dailyPlan: { greetingName: 'Alex' }, onPlayCoach: vi.fn() });
    expect(screen.getByTestId('daily-plan-skeleton')).toBeTruthy();
    const review = await screen.findByTestId('plan-review_last_game');
    expect(screen.queryByText(coach.promptAnalyze)).toBeNull();
    fireEvent.click(review);
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => u === '/api/coach/chat')).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([u]) => u === '/api/coach/chat')!;
    expect(JSON.parse(String(init!.body))).toMatchObject({ message: coach.planReviewPrompt, review_game_id: 'g1' });
  });

  it('«play the coach» opens the host’s play setup; hidden without one', async () => {
    vi.stubGlobal('fetch', fetchWith(FULL));
    const onPlayCoach = vi.fn();
    renderChat({ dailyPlan: {}, onPlayCoach });
    fireEvent.click(await screen.findByTestId('plan-play_coach'));
    expect(onPlayCoach).toHaveBeenCalled();
    cleanup();
    renderChat({ dailyPlan: {} });
    await screen.findByTestId('plan-review_last_game');
    expect(screen.queryByTestId('plan-play_coach')).toBeNull();
  });

  it('no plan (error or junk): the starter prompts, as before', async () => {
    vi.stubGlobal('fetch', fetchWith(null, false));
    renderChat({ dailyPlan: {}, onPlayCoach: vi.fn() });
    expect(await screen.findByText(coach.promptAnalyze)).toBeTruthy();
    cleanup();
    vi.stubGlobal('fetch', fetchWith({ kind: 'daily_plan', cards: [{ type: 'mystery' }] }));
    renderChat({ dailyPlan: {}, onPlayCoach: vi.fn() });
    expect(await screen.findByText(coach.promptAnalyze)).toBeTruthy();
  });

  it('peek on an empty session shows the compact plan', async () => {
    vi.stubGlobal('fetch', fetchWith(FULL));
    renderChat({ dailyPlan: {}, onPlayCoach: vi.fn(), view: 'peek' });
    const plan = await screen.findAllByTestId('daily-plan');
    expect(plan.some((p) => p.dataset.variant === 'peek')).toBe(true);
    expect(screen.queryByTestId('coach-peek')).toBeNull();
  });

  it('without the dailyPlan prop (review drawer) the plan is never fetched', () => {
    const fetchMock = fetchWith(FULL);
    vi.stubGlobal('fetch', fetchMock);
    renderChat();
    expect(screen.getByText(coach.promptAnalyze)).toBeTruthy();
    expect(fetchMock.mock.calls.some(([u]) => u === '/api/coach/daily-plan')).toBe(false);
  });
});
