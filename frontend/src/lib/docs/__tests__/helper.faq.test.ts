/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest';

import { FAQ_ITEMS, getFaqItems } from '../helper';

describe('getFaqItems', () => {
  it('returns the original FAQ_ITEMS array when appName is "Chesster" (apex)', () => {
    expect(getFaqItems('Chesster')).toBe(FAQ_ITEMS);
    expect(getFaqItems()).toBe(FAQ_ITEMS);
  });

  it('rewrites standalone "Chesster" mentions to the tenant brand name', () => {
    const tenant = getFaqItems('Chess Empire');
    const first = tenant[0];
    expect(first.question).toBe(
      'What is Chess Empire and how is it different from a chess coach?',
    );
    expect(first.answer).toContain('Chess Empire is your AI chess buddy');
  });

  it('does NOT rewrite "Chesster Cloud" (it is a product name)', () => {
    const tenant = getFaqItems('Chess Empire');
    const freeQuestion = tenant.find(i => i.question.includes('completely free'));
    expect(freeQuestion).toBeDefined();
    // The answer mentions "Chesster Cloud" — must stay literal.
    expect(freeQuestion!.answer).toContain('Chesster Cloud');
    // But standalone "Chesster" outside "Chesster Cloud" should be rewritten.
    const ratingQuestion = tenant.find(i => i.question.includes('improve my chess rating'));
    expect(ratingQuestion!.answer).not.toMatch(/\bChesster\b(?! Cloud)/);
  });
});
