/**
 * The chips under the conversation once it has started: derived from what
 * just happened (the last card's kind), what the board is doing (mode) and
 * whether a game is loaded — in that order of relevance. Pure: returns
 * message keys of the `coach` namespace; the chip text is also what is sent.
 * An empty session keeps the starter prompts instead (MessageList).
 */

import type { CoachMode } from './coach-mode';
import type { ToolSummaryKind } from './tool-summary';

export type ChipKey =
  | 'chipWhyThisMove'
  | 'chipAnotherLine'
  | 'chipReviewFirst'
  | 'chipTypicalPlans'
  | 'chipOpeningTraps'
  | 'chipAnotherPuzzle'
  | 'chipBiggestMistake'
  | 'chipEvaluate'
  | 'chipPlanHere'
  | 'chipPlayPlan'
  | 'chipThreats'
  | 'chipPuzzleHint'
  | 'chipPuzzleIdea'
  | 'chipReviewGame'
  | 'chipTurningPoint';

export const MAX_CHIPS = 4;

const BY_SUMMARY: Record<ToolSummaryKind, ChipKey[]> = {
  engine_line: ['chipWhyThisMove', 'chipAnotherLine'],
  game_list: ['chipReviewFirst'],
  opening: ['chipTypicalPlans', 'chipOpeningTraps'],
  puzzle: ['chipAnotherPuzzle'],
  critical_moments: ['chipBiggestMistake'],
  review_moments: ['chipBiggestMistake'],
};

const BY_MODE: Record<CoachMode, ChipKey[]> = {
  explore: ['chipEvaluate', 'chipPlanHere'],
  play: ['chipPlayPlan', 'chipThreats'],
  puzzle: ['chipPuzzleHint', 'chipPuzzleIdea'],
  viewer: ['chipReviewGame', 'chipTurningPoint'],
};

export interface ChipContext {
  mode: CoachMode;
  /** Kind of the latest card in the conversation, if any. */
  lastSummaryKind?: ToolSummaryKind | null;
  /** A game (moves, not just a position) is on the study board. */
  gameLoaded: boolean;
}

export function contextChips({ mode, lastSummaryKind, gameLoaded }: ChipContext): ChipKey[] {
  const keys: ChipKey[] = [
    ...(lastSummaryKind ? BY_SUMMARY[lastSummaryKind] ?? [] : []),
    ...BY_MODE[mode],
    // A loaded game is worth a review — except mid-game or mid-puzzle.
    ...(gameLoaded && mode === 'explore' ? (['chipReviewGame'] as ChipKey[]) : []),
    'chipAnotherPuzzle',
  ];
  return [...new Set(keys)].slice(0, MAX_CHIPS);
}
