import { describe, it, expect } from 'vitest';
import { MAX_CHIPS, contextChips } from '../context-chips';

describe('contextChips', () => {
  it('leads with what the last card invites', () => {
    expect(contextChips({ mode: 'explore', lastSummaryKind: 'engine_line', gameLoaded: false })).toEqual([
      'chipWhyThisMove',
      'chipAnotherLine',
      'chipEvaluate',
      'chipPlanHere',
    ]);
    expect(contextChips({ mode: 'explore', lastSummaryKind: 'game_list', gameLoaded: false })[0]).toBe('chipReviewFirst');
    expect(contextChips({ mode: 'explore', lastSummaryKind: 'review_moments', gameLoaded: true })[0]).toBe('chipBiggestMistake');
    expect(contextChips({ mode: 'explore', lastSummaryKind: 'opening', gameLoaded: false }).slice(0, 2)).toEqual([
      'chipTypicalPlans',
      'chipOpeningTraps',
    ]);
  });

  it('follows the mode without a card', () => {
    expect(contextChips({ mode: 'play', gameLoaded: true })).toEqual(['chipPlayPlan', 'chipThreats', 'chipAnotherPuzzle']);
    expect(contextChips({ mode: 'puzzle', gameLoaded: false }).slice(0, 2)).toEqual(['chipPuzzleHint', 'chipPuzzleIdea']);
    expect(contextChips({ mode: 'viewer', gameLoaded: false }).slice(0, 2)).toEqual(['chipReviewGame', 'chipTurningPoint']);
  });

  it('offers a review when a game is loaded in explore', () => {
    expect(contextChips({ mode: 'explore', gameLoaded: true })).toContain('chipReviewGame');
    expect(contextChips({ mode: 'explore', gameLoaded: false })).not.toContain('chipReviewGame');
  });

  it('never repeats a chip and never shows more than four', () => {
    for (const kind of ['engine_line', 'game_list', 'opening', 'puzzle', 'critical_moments', 'review_moments', null] as const) {
      for (const mode of ['explore', 'play', 'puzzle', 'viewer'] as const) {
        const chips = contextChips({ mode, lastSummaryKind: kind, gameLoaded: true });
        expect(chips.length).toBeLessThanOrEqual(MAX_CHIPS);
        expect(new Set(chips).size).toBe(chips.length);
      }
    }
  });
});
