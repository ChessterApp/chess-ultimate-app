/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest';

import en from '../../messages/en.json';
import ru from '../../messages/ru.json';
import kz from '../../messages/kz.json';

import { TUG_LEVELS, TUG_THEMES } from '../lib/tug-of-war/prefetch';

type Json = string | Json[] | { [key: string]: Json };

const locales: Record<string, { tugOfWar?: Json }> = { en, ru, kz };

/** Deep-flatten a namespace into dot/index keys, e.g. `how.0`, `levels.pawn`. */
function flatten(value: Json, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  if (typeof value === 'string') {
    out[prefix] = value;
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => Object.assign(out, flatten(v, prefix ? `${prefix}.${i}` : String(i))));
  } else {
    for (const [k, v] of Object.entries(value)) {
      Object.assign(out, flatten(v, prefix ? `${prefix}.${k}` : k));
    }
  }
  return out;
}

describe('tugOfWar namespace i18n', () => {
  it('exists in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      expect(messages.tugOfWar, `tugOfWar namespace missing in ${locale}.json`).toBeDefined();
    }
  });

  it('has identical key sets across en / ru / kz', () => {
    const enKeys = Object.keys(flatten(en.tugOfWar as Json)).sort();
    const ruKeys = Object.keys(flatten(ru.tugOfWar as Json)).sort();
    const kzKeys = Object.keys(flatten(kz.tugOfWar as Json)).sort();

    expect(ruKeys).toEqual(enKeys);
    expect(kzKeys).toEqual(enKeys);
  });

  it('covers every difficulty level and theme in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.tugOfWar ?? {});
      for (const level of TUG_LEVELS) {
        expect(flat[`levels.${level.id}`], `${locale}.tugOfWar.levels.${level.id} missing`).toBeTruthy();
      }
      for (const theme of TUG_THEMES) {
        expect(flat[`themes.${theme.tag}`], `${locale}.tugOfWar.themes.${theme.tag} missing`).toBeTruthy();
      }
    }
  });

  it('has four how-to-play bullet lines in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const how = (messages.tugOfWar as { how?: unknown })?.how;
      expect(Array.isArray(how), `${locale}.tugOfWar.how must be an array`).toBe(true);
      expect((how as string[]).length, `${locale}.tugOfWar.how must have 4 lines`).toBe(4);
    }
  });

  it('keeps the {team} placeholder in the win banner across locales', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const wins = (messages.tugOfWar as { wins?: string })?.wins ?? '';
      expect(wins, `${locale}.tugOfWar.wins must interpolate {team}`).toContain('{team}');
    }
  });

  it('does not leave ru / kz values identical to English (untranslated)', () => {
    const enFlat = flatten(en.tugOfWar as Json);
    const ruFlat = flatten(ru.tugOfWar as Json);
    const kzFlat = flatten(kz.tugOfWar as Json);

    for (const [key, value] of Object.entries(enFlat)) {
      expect(ruFlat[key], `ru.tugOfWar.${key} left untranslated`).not.toBe(value);
      expect(kzFlat[key], `kz.tugOfWar.${key} left untranslated`).not.toBe(value);
    }
  });

  it('has non-empty string values everywhere', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.tugOfWar ?? {});
      for (const [key, value] of Object.entries(flat)) {
        expect(typeof value, `${locale}.tugOfWar.${key} must be a string`).toBe('string');
        expect(value.trim().length, `${locale}.tugOfWar.${key} must not be empty`).toBeGreaterThan(0);
      }
    }
  });
});
