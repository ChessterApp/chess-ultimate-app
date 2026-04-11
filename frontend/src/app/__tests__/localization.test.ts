import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';

const messagesDir = path.resolve(__dirname, '../../../messages');
const locales = ['en', 'ru', 'kz'] as const;

function loadMessages(locale: string): Record<string, unknown> {
  const filePath = path.join(messagesDir, `${locale}.json`);
  return JSON.parse(fs.readFileSync(filePath, 'utf-8'));
}

function getAllKeys(obj: Record<string, unknown>, prefix = ''): Set<string> {
  const keys = new Set<string>();
  for (const [k, v] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const subKey of getAllKeys(v as Record<string, unknown>, fullKey)) {
        keys.add(subKey);
      }
    } else {
      keys.add(fullKey);
    }
  }
  return keys;
}

describe('Localization files', () => {
  const messages: Record<string, Record<string, unknown>> = {};
  const keysByLocale: Record<string, Set<string>> = {};

  for (const locale of locales) {
    messages[locale] = loadMessages(locale);
    keysByLocale[locale] = getAllKeys(messages[locale]);
  }

  it('all locale files should be valid JSON', () => {
    for (const locale of locales) {
      expect(messages[locale]).toBeDefined();
      expect(typeof messages[locale]).toBe('object');
    }
  });

  it('all locales should have the same number of keys', () => {
    const enCount = keysByLocale.en.size;
    for (const locale of locales) {
      expect(keysByLocale[locale].size, `${locale} has ${keysByLocale[locale].size} keys, expected ${enCount}`).toBe(enCount);
    }
  });

  it('ru should have all keys from en', () => {
    const missing = [...keysByLocale.en].filter(k => !keysByLocale.ru.has(k));
    expect(missing, `RU missing keys: ${missing.join(', ')}`).toEqual([]);
  });

  it('kz should have all keys from en', () => {
    const missing = [...keysByLocale.en].filter(k => !keysByLocale.kz.has(k));
    expect(missing, `KZ missing keys: ${missing.join(', ')}`).toEqual([]);
  });

  it('no locale should have extra keys not in en', () => {
    for (const locale of ['ru', 'kz'] as const) {
      const extra = [...keysByLocale[locale]].filter(k => !keysByLocale.en.has(k));
      expect(extra, `${locale.toUpperCase()} has extra keys: ${extra.join(', ')}`).toEqual([]);
    }
  });

  it('no translation values should be empty strings', () => {
    for (const locale of locales) {
      const emptyKeys: string[] = [];
      function checkEmpty(obj: Record<string, unknown>, prefix = '') {
        for (const [k, v] of Object.entries(obj)) {
          const fullKey = prefix ? `${prefix}.${k}` : k;
          if (v && typeof v === 'object' && !Array.isArray(v)) {
            checkEmpty(v as Record<string, unknown>, fullKey);
          } else if (v === '') {
            emptyKeys.push(fullKey);
          }
        }
      }
      checkEmpty(messages[locale]);
      expect(emptyKeys, `${locale.toUpperCase()} has empty values: ${emptyKeys.join(', ')}`).toEqual([]);
    }
  });

  it('simple placeholders should be consistent across locales', () => {
    // Extract top-level simple placeholders like {name}, {count}, {rating}
    // Skip strings that are entirely ICU plural/select expressions
    function getSimplePlaceholders(str: string): Set<string> {
      // If the string is an ICU plural/select expression, extract only the variable name
      if (/^\{(\w+),\s*(?:plural|select|selectordinal)/.test(str)) {
        return new Set();
      }
      const placeholders = new Set<string>();
      // Match {word} but not inside ICU plural branches
      for (const match of str.matchAll(/\{(\w+)\}/g)) {
        const name = match[1];
        if (!isNaN(Number(name))) continue; // Skip numeric like {0}, {1}
        placeholders.add(name);
      }
      return placeholders;
    }

    const inconsistent: string[] = [];

    for (const key of keysByLocale.en) {
      const enVal = getNestedValue(messages.en, key);
      if (typeof enVal !== 'string') continue;

      const enPlaceholders = getSimplePlaceholders(enVal);
      if (enPlaceholders.size === 0) continue;

      for (const locale of ['ru', 'kz'] as const) {
        const localeVal = getNestedValue(messages[locale], key);
        if (typeof localeVal !== 'string') continue;

        const localePlaceholders = getSimplePlaceholders(localeVal);
        for (const ph of enPlaceholders) {
          if (!localePlaceholders.has(ph)) {
            inconsistent.push(`${locale}.${key} missing placeholder {${ph}}`);
          }
        }
      }
    }
    expect(inconsistent, `Placeholder mismatches:\n${inconsistent.join('\n')}`).toEqual([]);
  });
});

describe('i18n config', () => {
  it('config exports correct locales', async () => {
    const config = await import('@/i18n/config');
    expect(config.locales).toEqual(['en', 'ru', 'kz']);
    expect(config.defaultLocale).toBe('en');
  });

  it('every configured locale has a messages file', async () => {
    const config = await import('@/i18n/config');
    for (const locale of config.locales) {
      const filePath = path.join(messagesDir, `${locale}.json`);
      expect(fs.existsSync(filePath), `Missing messages file for locale: ${locale}`).toBe(true);
    }
  });

  it('localeNames has entries for all locales', async () => {
    const config = await import('@/i18n/config');
    for (const locale of config.locales) {
      expect(config.localeNames[locale]).toBeDefined();
      expect(config.localeNames[locale].length).toBeGreaterThan(0);
    }
  });
});

describe('Clerk localization', () => {
  it('layout exports Clerk localizations for all supported locales', async () => {
    // Read the layout file and verify it contains localization for all 3 locales
    const layoutPath = path.resolve(__dirname, '../layout.tsx');
    const layoutContent = fs.readFileSync(layoutPath, 'utf-8');

    for (const locale of locales) {
      expect(layoutContent, `Layout missing Clerk localization for ${locale}`).toContain(`${locale}: {`);
    }

    // Verify each locale has signIn and signUp sections
    expect(layoutContent).toContain('signIn:');
    expect(layoutContent).toContain('signUp:');
  });
});

function getNestedValue(obj: Record<string, unknown>, key: string): unknown {
  const parts = key.split('.');
  let current: unknown = obj;
  for (const part of parts) {
    if (current && typeof current === 'object' && !Array.isArray(current)) {
      current = (current as Record<string, unknown>)[part];
    } else {
      return undefined;
    }
  }
  return current;
}
