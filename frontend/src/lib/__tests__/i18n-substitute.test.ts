/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest';

import { substituteAppName } from '@/lib/i18n-substitute';
import enMessages from '../../../messages/en.json';

describe('substituteAppName', () => {
  it('replaces {appName} in flat strings', () => {
    expect(substituteAppName('Welcome to {appName}', 'Chess Empire')).toBe(
      'Welcome to Chess Empire',
    );
  });

  it('replaces {appName} in nested object trees', () => {
    const input = {
      a: 'Hello {appName}',
      b: { c: 'About {appName}', d: ['inside {appName}', 'plain'] },
      e: 42,
      f: null,
    };
    expect(substituteAppName(input, 'Chess Empire')).toEqual({
      a: 'Hello Chess Empire',
      b: { c: 'About Chess Empire', d: ['inside Chess Empire', 'plain'] },
      e: 42,
      f: null,
    });
  });

  it('falls back cleanly to Chesster when applied with the apex default', () => {
    const out = substituteAppName(enMessages, 'Chesster');
    expect(out.common.chesster).toBe('Chesster');
    expect(out.upgradePrompt.description).toContain('Chesster');
    expect(out.schoolOnboarding.account.notSignedInSubtitle).toBe(
      'Create your Chesster account to begin.',
    );
    expect(out.schoolOnboarding.plan.studentsQuestion).toBe(
      'How many students will you have on Chesster?',
    );
  });

  it('substitutes the tenant brand name across all replaced keys', () => {
    const out = substituteAppName(enMessages, 'Chess Empire');
    expect(out.common.chesster).toBe('Chess Empire');
    expect(out.schoolOnboarding.shell.chesster).toBe('Chess Empire');
    expect(out.schoolOnboarding.account.notSignedInSubtitle).toBe(
      'Create your Chess Empire account to begin.',
    );
    expect(out.schoolOnboarding.plan.studentsQuestion).toBe(
      'How many students will you have on Chess Empire?',
    );
    expect(out.schoolOnboarding.marketing.metaTitle).toBe(
      'Chess Empire for Schools — Launch your branded chess platform',
    );
    // Sanity: no orphan placeholders remain in any tenant-visible string.
    const json = JSON.stringify(out);
    expect(json.includes('{appName}')).toBe(false);
  });
});
