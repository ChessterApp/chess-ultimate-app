import { describe, it, expect } from 'vitest';
import { answerBucket, onboardingEntry, stepCompletedProps } from '../analytics';

describe('answerBucket()', () => {
  it('passes enum option keys through', () => {
    expect(answerBucket(2, { attribution: 'socialMedia' })).toBe('socialMedia');
    expect(answerBucket(9, { practiceTime: '15min' })).toBe('15min');
    expect(answerBucket(10, { goal: 'beatFriends' })).toBe('beatFriends');
  });

  it('never leaks the platform username', () => {
    expect(answerBucket(5, { platformUsername: 'magnus_kid_2015' })).toBe('provided');
    expect(answerBucket(5, {})).toBe('skipped');
  });

  it('collapses anything that is not an identifier to "other"', () => {
    expect(answerBucket(8, { challenge: 'my name is Ann, I am 9' })).toBe('other');
  });

  it('buckets ratings into bands', () => {
    expect(answerBucket(6, { noRating: true, eloRating: 1500 })).toBe('none');
    expect(answerBucket(6, { eloRating: 800 })).toBe('800_1199');
    expect(answerBucket(6, { onlineRating: 1700, eloRating: 600 })).toBe('1600_plus');
    expect(answerBucket(6, { eloRating: 500 })).toBe('lt_800');
  });

  it('sorts multi-select focus areas', () => {
    expect(answerBucket(7, { focusAreas: ['tactics', 'endgames'] })).toBe('endgames,tactics');
    expect(answerBucket(7, { focusAreas: [] })).toBeUndefined();
  });

  it('has no bucket for non-question steps', () => {
    expect(answerBucket(1, {})).toBeUndefined();
    expect(answerBucket(13, {})).toBeUndefined();
  });
});

describe('stepCompletedProps()', () => {
  it('names the step and omits an empty bucket', () => {
    expect(stepCompletedProps(3, { experience: 'beginner' })).toEqual({
      step_index: 3,
      step_name: 'experience',
      answer_bucket: 'beginner',
    });
    expect(stepCompletedProps(1, {})).toEqual({ step_index: 1, step_name: 'welcome' });
  });
});

describe('onboardingEntry()', () => {
  const origin = 'https://chesster.io';
  it('classifies UTM / click-id traffic as ad', () => {
    expect(onboardingEntry('?utm_source=telegram', '', origin)).toBe('ad');
    expect(onboardingEntry('?fbclid=x', `${origin}/`, origin)).toBe('ad');
  });
  it('same-origin referrer is landing, otherwise direct', () => {
    expect(onboardingEntry('', `${origin}/`, origin)).toBe('landing');
    expect(onboardingEntry('', 'https://google.com/', origin)).toBe('direct');
    expect(onboardingEntry('', '', origin)).toBe('direct');
  });
});
