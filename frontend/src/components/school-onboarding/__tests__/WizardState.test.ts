import { describe, it, expect } from 'vitest';
import { slugify } from '../WizardState';

describe('slugify', () => {
  it('lowercases and replaces spaces with hyphens', () => {
    expect(slugify('Almaty Chess Academy')).toBe('almaty-chess-academy');
  });

  it('collapses multiple separators', () => {
    expect(slugify('  Foo   Bar  ')).toBe('foo-bar');
  });

  it('strips disallowed characters', () => {
    expect(slugify('Café Düsseldorf!')).toBe('caf-d-sseldorf');
  });

  it('trims leading/trailing hyphens', () => {
    expect(slugify('--abc--')).toBe('abc');
  });

  it('caps length at 30', () => {
    const long = 'a'.repeat(50);
    expect(slugify(long).length).toBe(30);
  });

  it('returns empty string for empty input', () => {
    expect(slugify('')).toBe('');
  });
});
