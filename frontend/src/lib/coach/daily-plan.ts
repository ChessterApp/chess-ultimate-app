/**
 * The daily-plan home (coach redesign P3b): how the plan's cards are laid
 * out and what each one does. Pure; the component (DailyPlan) renders it.
 */

import type { DailyPlan, DailyPlanCard } from './tool-summary';

/** Puzzle themes (Lichess tags) with a label; another theme is offered as puzzles on any theme. */
export const THEME_KEYS: Record<string, string> = {
  opening: 'planThemeOpening',
  middlegame: 'planThemeMiddlegame',
  endgame: 'planThemeEndgame',
  fork: 'planThemeFork',
  pin: 'planThemePin',
  skewer: 'planThemeSkewer',
  mate: 'planThemeMate',
  mateIn1: 'planThemeMateIn1',
  mateIn2: 'planThemeMateIn2',
  hangingPiece: 'planThemeHangingPiece',
  discoveredAttack: 'planThemeDiscoveredAttack',
  backRankMate: 'planThemeBackRankMate',
  sacrifice: 'planThemeSacrifice',
  deflection: 'planThemeDeflection',
};

type WeakSpot = Extract<DailyPlanCard, { type: 'weak_spot' }>;

/** A weak spot as shown: its theme's label key, or none (and then no stat: it was about that theme). */
export function weakSpotView(card: WeakSpot): { themeKey: string | null; stat: WeakSpot['stat'] } {
  const themeKey = (card.theme && THEME_KEYS[card.theme]) || null;
  return { themeKey, stat: themeKey ? card.stat : undefined };
}

/** The plan without the cards this host cannot act on (no play sheet → no «play the coach»); null if none is left. */
export function playablePlan(plan: DailyPlan, canPlay: boolean): DailyPlan | null {
  if (canPlay) return plan.cards.length ? plan : null;
  const cards = plan.cards.filter((c) => c.type !== 'play_coach');
  return cards.length ? { ...plan, cards } : null;
}

export interface PlanLayout {
  /** The big card: the first one (the last game's review when there is one). */
  primary: DailyPlanCard;
  /** The weak-spot card under it, when it is not the primary. */
  spot: WeakSpot | null;
  /** The small tiles in one row: the opening lesson, playing the coach. */
  tiles: DailyPlanCard[];
}

export function planLayout(plan: DailyPlan): PlanLayout {
  const [primary, ...rest] = plan.cards;
  const spot = (rest.find((c) => c.type === 'weak_spot') as WeakSpot | undefined) ?? null;
  return { primary, spot, tiles: rest.filter((c) => c !== spot).slice(0, 2) };
}

export type PlanAction =
  | { kind: 'send'; text: string; reviewGameId?: string }
  /** Open the play setup sheet. */
  | { kind: 'play' };

type Translate = (key: string, values?: Record<string, string | number>) => string;

/** What tapping a card does: a message to the coach (the review carries its game's id) or the play sheet. */
export function planAction(card: DailyPlanCard, t: Translate): PlanAction {
  switch (card.type) {
    case 'review_last_game':
      return { kind: 'send', text: t('planReviewPrompt'), reviewGameId: card.game_id };
    case 'weak_spot': {
      const { themeKey } = weakSpotView(card);
      return { kind: 'send', text: themeKey ? t('planSpotPrompt', { theme: t(themeKey) }) : t('promptPuzzle') };
    }
    case 'opening_lesson':
      return { kind: 'send', text: t('planOpeningPrompt', { name: card.name, eco: card.eco }) };
    case 'play_coach':
      return { kind: 'play' };
  }
}
