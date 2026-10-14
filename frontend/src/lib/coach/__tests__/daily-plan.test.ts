import { describe, it, expect } from 'vitest';
import { planAction, planLayout, playablePlan, weakSpotView } from '../daily-plan';
import type { DailyPlan } from '../tool-summary';

const t = (key: string, values?: Record<string, string | number>) => (values ? `${key}${JSON.stringify(values)}` : key);

const REVIEW = { type: 'review_last_game' as const, game_id: 'g1', title: 'Me – Bot', moments_count: 3 };
const SPOT = { type: 'weak_spot' as const, puzzles: 5, theme: 'endgame', stat: { games_with: 4, games: 10 } };
const OPENING = { type: 'opening_lesson' as const, eco: 'C50', name: 'Italian Game' };
const PLAY = { type: 'play_coach' as const };

describe('planLayout', () => {
  it('full plan: the review leads, the weak spot under it, opening and play as tiles', () => {
    const plan: DailyPlan = { kind: 'daily_plan', cards: [REVIEW, SPOT, OPENING, PLAY] };
    expect(planLayout(plan)).toEqual({ primary: REVIEW, spot: SPOT, tiles: [OPENING, PLAY] });
  });

  it('minimal plan: the puzzles lead, play is a tile', () => {
    const generic = { type: 'weak_spot' as const, puzzles: 5 };
    expect(planLayout({ kind: 'daily_plan', cards: [generic, PLAY] })).toEqual({ primary: generic, spot: null, tiles: [PLAY] });
  });
});

describe('weakSpotView', () => {
  it('a known theme keeps its stat; an unknown one is puzzles on any theme, without the stat', () => {
    expect(weakSpotView(SPOT)).toEqual({ themeKey: 'planThemeEndgame', stat: SPOT.stat });
    expect(weakSpotView({ ...SPOT, theme: 'zugzwangish' })).toEqual({ themeKey: null, stat: undefined });
    expect(weakSpotView({ type: 'weak_spot', puzzles: 5 })).toEqual({ themeKey: null, stat: undefined });
  });
});

describe('planAction', () => {
  it('each card does its one thing', () => {
    expect(planAction(REVIEW, t)).toEqual({ kind: 'send', text: 'planReviewPrompt', reviewGameId: 'g1' });
    expect(planAction(SPOT, t)).toEqual({ kind: 'send', text: 'planSpotPrompt{"theme":"planThemeEndgame"}' });
    expect(planAction({ type: 'weak_spot', puzzles: 5 }, t)).toEqual({ kind: 'send', text: 'promptPuzzle' });
    expect(planAction(OPENING, t)).toEqual({ kind: 'send', text: 'planOpeningPrompt{"name":"Italian Game","eco":"C50"}' });
    expect(planAction(PLAY, t)).toEqual({ kind: 'play' });
  });
});

describe('playablePlan', () => {
  it('drops «play the coach» where there is no play sheet, and is null when nothing is left', () => {
    const plan: DailyPlan = { kind: 'daily_plan', cards: [SPOT, PLAY] };
    expect(playablePlan(plan, true)).toBe(plan);
    expect(playablePlan(plan, false)?.cards).toEqual([SPOT]);
    expect(playablePlan({ kind: 'daily_plan', cards: [PLAY] }, false)).toBeNull();
  });
});
