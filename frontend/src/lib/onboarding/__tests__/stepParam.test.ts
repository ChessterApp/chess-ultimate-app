import { describe, it, expect } from 'vitest';
import { parseStepParam } from '../stepParam';

describe('parseStepParam', () => {
  it.each([
    [null, 1],
    ['', 1],
    ['3', 3],
    ['16', 16],
    ['complete', 'complete'],
    ['abc', 'resume'],
    ['0', 'resume'],
    ['-2', 'resume'],
    ['3abc', 'resume'],
  ])('%j → %j', (raw, expected) => {
    expect(parseStepParam(raw)).toBe(expected);
  });
});
