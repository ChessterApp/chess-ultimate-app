/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest';

import en from '../../messages/en.json';
import ru from '../../messages/ru.json';
import kz from '../../messages/kz.json';

type Messages = { coach?: Record<string, unknown> };

const locales: Record<string, Messages> = { en, ru, kz };

describe('coach namespace i18n', () => {
  it('exists in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      expect(messages.coach, `coach namespace missing in ${locale}.json`).toBeDefined();
    }
  });

  it('has identical key sets across en / ru / kz', () => {
    const enKeys = Object.keys(en.coach).sort();
    const ruKeys = Object.keys(ru.coach).sort();
    const kzKeys = Object.keys(kz.coach).sort();

    expect(ruKeys).toEqual(enKeys);
    expect(kzKeys).toEqual(enKeys);
  });

  it('has non-empty string values for every key in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const coach = messages.coach ?? {};
      for (const [key, value] of Object.entries(coach)) {
        expect(typeof value, `${locale}.coach.${key} must be a string`).toBe('string');
        expect((value as string).trim().length, `${locale}.coach.${key} must not be empty`).toBeGreaterThan(0);
      }
    }
  });

  it('does not leave ru / kz values identical to English (untranslated)', () => {
    // ECO is a language-neutral code and is intentionally identical.
    const allowedIdentical = new Set(['tableEco']);
    for (const [key, enValue] of Object.entries(en.coach)) {
      if (allowedIdentical.has(key)) continue;
      const ruValue = (ru.coach as Record<string, string>)[key];
      const kzValue = (kz.coach as Record<string, string>)[key];
      expect(ruValue, `ru.coach.${key} looks untranslated`).not.toBe(enValue);
      expect(kzValue, `kz.coach.${key} looks untranslated`).not.toBe(enValue);
    }
  });
});
