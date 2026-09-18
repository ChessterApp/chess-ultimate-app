/**
 * Locale-parity guard for the `family` namespace: every locale file must carry
 * the identical key set so no Family-card string silently falls back.
 */
import { describe, it, expect } from 'vitest';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';

function keyPaths(obj: Record<string, unknown>, prefix = ''): string[] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    return v && typeof v === 'object' && !Array.isArray(v)
      ? keyPaths(v as Record<string, unknown>, path)
      : [path];
  });
}

describe('family message parity', () => {
  const enKeys = keyPaths(en.family).sort();

  it('en has a non-empty family namespace', () => {
    expect(enKeys.length).toBeGreaterThan(0);
  });

  it('ru carries the identical family key set', () => {
    expect(keyPaths(ru.family).sort()).toEqual(enKeys);
  });

  it('kz carries the identical family key set', () => {
    expect(keyPaths(kz.family).sort()).toEqual(enKeys);
  });
});
