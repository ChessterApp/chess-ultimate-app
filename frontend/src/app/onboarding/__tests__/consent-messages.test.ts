import { describe, it, expect } from 'vitest';
import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';

const KEYS = ['parentConsent', 'parentConsentRequired'] as const;

describe('parent consent copy (F8) — en/ru/kz parity', () => {
  for (const [locale, messages] of Object.entries({ en, ru, kz })) {
    it(`${locale} has every consent key, non-empty`, () => {
      const plan = (messages as any).onboarding.customPlan;
      for (const key of KEYS) {
        expect(typeof plan[key], `${locale}.${key}`).toBe('string');
        expect(plan[key].trim().length).toBeGreaterThan(0);
      }
    });

    it(`${locale} consent label links Terms and Privacy`, () => {
      const label: string = (messages as any).onboarding.customPlan.parentConsent;
      expect(label).toMatch(/<terms>.+<\/terms>/);
      expect(label).toMatch(/<privacy>.+<\/privacy>/);
    });
  }
});
