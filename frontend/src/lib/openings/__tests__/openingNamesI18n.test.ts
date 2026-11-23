import { describe, it, expect } from 'vitest';
import { translateOpeningName } from '../openingNamesI18n';

describe('translateOpeningName', () => {
  it('translates the opening family for ru and keeps the variation', () => {
    expect(translateOpeningName('Sicilian Defense: Bowdler Attack', 'ru')).toBe(
      'Сицилианская защита: Bowdler Attack',
    );
  });

  it('leaves English untouched', () => {
    expect(translateOpeningName('Sicilian Defense: Bowdler Attack', 'en')).toBe(
      'Sicilian Defense: Bowdler Attack',
    );
  });
});
