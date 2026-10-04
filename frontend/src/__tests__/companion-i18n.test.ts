/**
 * @vitest-environment node
 *
 * Parity guard for the `companion` namespace (Companion Phase 1). Ensures
 * en / ru / kz stay in lockstep: same key set, all non-empty strings, and
 * identical ICU placeholders. Mirrors gameReview-i18n.test.ts.
 */
import { describe, it, expect } from 'vitest';

import en from '../../messages/en.json';
import ru from '../../messages/ru.json';
import kz from '../../messages/kz.json';

const locales: Record<string, Record<string, unknown>> = { en, ru, kz };

function flatten(obj: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {};
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const key = prefix ? `${prefix}.${k}` : k;
      if (v && typeof v === 'object') Object.assign(out, flatten(v, key));
      else out[key] = String(v);
    }
  }
  return out;
}

function placeholders(value: string): string[] {
  const names = new Set<string>();
  const re = /\{(\w+)/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(value)) !== null) names.add(m[1]);
  return [...names].sort();
}

// Every key the Phase 1 surface reads at render time.
const REQUIRED_KEYS = [
  'title',
  'subtitle',
  'notLinkedTitle',
  'notLinkedBody',
  'eggAlt',
  'eggs.fox',
  'eggs.owl',
  'eggs.turtle',
  'eggs.dragon',
  'chooseEgg.title',
  'chooseEgg.subtitle',
  'chooseEgg.saving',
  'ring.title',
  'ring.count',
  'ring.hatchReady',
  'ring.keepGoing',
  // Phase 2 — assessment pipeline strings.
  'assessment.correct',
  'assessment.incorrect',
  'assessment.hintButton',
  'assessment.hintUsed',
  'assessment.reward',
  'assessment.demonstrated',
  'assessment.nextTask',
  // Phase 3 — hatch + fox reveal strings.
  'hatch.cta',
  'hatch.nameLabel',
  'hatch.namePlaceholder',
  'hatch.subtitle',
  'hatch.confirm',
  'hatch.hatching',
  'hatch.skip',
  'hatch.replay',
  'hatch.title',
  'hatch.reward',
  'hatch.starter',
  'hatch.continue',
  'hatch.foxAlt',
  'hatch.nameRequired',
  'hatch.notReady',
  'hatch.failed',
  // Phase 4 — Watchtower chapter strings.
  'watchtower.title',
  'watchtower.progress',
  'watchtower.play',
  'watchtower.replay',
  'watchtower.submit',
  'watchtower.clear',
  'watchtower.correct',
  'watchtower.incorrect',
  'watchtower.back',
  'watchtower.chapterComplete',
  'watchtower.chapterReward',
  // Phase 4 — due-review strings.
  'review.title',
  'review.subtitle',
  'review.submit',
  'review.clear',
  'review.correct',
  'review.incorrect',
  'review.back',
  'review.allCaught',
  'review.rung',
  'review.start',
  // Phase 5 — weekly-goal strings.
  'goal.title',
  'goal.targetLabel',
  'goal.progress',
  'goal.met',
  'goal.keepGoing',
  // Phase 5 — quest strip strings.
  'quest.title',
  'quest.start',
  'quest.active',
  'quest.completed',
  'quest.progress',
  'quest.reward',
];

describe('companion namespace i18n', () => {
  it('exists in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      expect(messages.companion, `companion namespace missing in ${locale}.json`).toBeDefined();
    }
  });

  it('has every required key with a non-empty string in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.companion);
      for (const key of REQUIRED_KEYS) {
        expect(typeof flat[key], `${locale}.companion.${key} must be a string`).toBe('string');
        expect(
          flat[key]?.trim().length,
          `${locale}.companion.${key} must not be empty`,
        ).toBeGreaterThan(0);
      }
    }
  });

  it('has identical (recursively-flattened) key sets across en / ru / kz', () => {
    const enKeys = Object.keys(flatten(en.companion)).sort();
    const ruKeys = Object.keys(flatten(ru.companion)).sort();
    const kzKeys = Object.keys(flatten(kz.companion)).sort();
    expect(ruKeys).toEqual(enKeys);
    expect(kzKeys).toEqual(enKeys);
  });

  it('preserves ICU placeholders identically across every locale', () => {
    const enFlat = flatten(en.companion);
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.companion);
      for (const [key, value] of Object.entries(enFlat)) {
        expect(
          placeholders(flat[key]),
          `${locale}.companion.${key} placeholders must match en`,
        ).toEqual(placeholders(value));
      }
    }
  });

  it('keeps the {name} and {done}/{total} placeholders', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.companion);
      expect(flat['eggAlt'], `${locale} eggAlt {name}`).toContain('{name}');
      expect(flat['ring.count'], `${locale} ring.count {done}`).toContain('{done}');
      expect(flat['ring.count'], `${locale} ring.count {total}`).toContain('{total}');
    }
  });
});
