/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest';

import en from '../../messages/en.json';
import ru from '../../messages/ru.json';
import kz from '../../messages/kz.json';

import { BOTS } from '../data/bots';

type Leaf = string;
type Namespace = Record<string, Leaf | Record<string, Leaf>>;

const locales: Record<string, { bots?: Namespace }> = { en, ru, kz };

/** Flatten one level of nesting into dot keys, e.g. `luna-1100.description`. */
function flatten(ns: Namespace): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(ns)) {
    if (typeof value === 'string') {
      out[key] = value;
    } else {
      for (const [sub, v] of Object.entries(value)) out[`${key}.${sub}`] = v;
    }
  }
  return out;
}

describe('bots namespace i18n', () => {
  it('exists in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      expect(messages.bots, `bots namespace missing in ${locale}.json`).toBeDefined();
    }
  });

  it('covers every bot defined in bots.ts (description + playStyle) in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.bots ?? {});
      for (const bot of BOTS) {
        expect(flat[`${bot.id}.description`], `${locale}.bots.${bot.id}.description missing`).toBeTruthy();
        expect(flat[`${bot.id}.playStyle`], `${locale}.bots.${bot.id}.playStyle missing`).toBeTruthy();
      }
    }
  });

  it('localizes all tier labels in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const tiers = (messages.bots?.tiers ?? {}) as Record<string, string>;
      for (const tier of ['beginner', 'intermediate', 'advanced', 'master']) {
        expect(tiers[tier], `${locale}.bots.tiers.${tier} missing`).toBeTruthy();
      }
    }
  });

  it('has identical key sets across en / ru / kz', () => {
    const enKeys = Object.keys(flatten(en.bots as Namespace)).sort();
    const ruKeys = Object.keys(flatten(ru.bots as Namespace)).sort();
    const kzKeys = Object.keys(flatten(kz.bots as Namespace)).sort();

    expect(ruKeys).toEqual(enKeys);
    expect(kzKeys).toEqual(enKeys);
  });

  it('does not leave ru / kz values identical to English (untranslated)', () => {
    const enFlat = flatten(en.bots as Namespace);
    const ruFlat = flatten(ru.bots as Namespace);
    const kzFlat = flatten(kz.bots as Namespace);

    for (const [key, value] of Object.entries(enFlat)) {
      expect(ruFlat[key], `ru.bots.${key} left untranslated`).not.toBe(value);
      expect(kzFlat[key], `kz.bots.${key} left untranslated`).not.toBe(value);
    }
  });

  it('has non-empty string values everywhere', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.bots ?? {});
      for (const [key, value] of Object.entries(flat)) {
        expect(typeof value, `${locale}.bots.${key} must be a string`).toBe('string');
        expect(value.trim().length, `${locale}.bots.${key} must not be empty`).toBeGreaterThan(0);
      }
    }
  });
});
