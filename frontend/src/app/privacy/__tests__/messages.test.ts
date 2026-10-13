/**
 * Locale-parity guard for the T0b namespaces (`privacy`, `upgradeSuccess`):
 * every locale must carry the identical, non-empty key set.
 */
import { describe, it, expect } from 'vitest';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';

function leaves(obj: Record<string, unknown>, prefix = ''): [string, unknown][] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const path = prefix ? `${prefix}.${k}` : k;
    return v && typeof v === 'object' && !Array.isArray(v)
      ? leaves(v as Record<string, unknown>, path)
      : [[path, v] as [string, unknown]];
  });
}

describe.each(['privacy', 'upgradeSuccess'] as const)('%s message parity', (ns) => {
  const enKeys = leaves(en[ns]).map(([k]) => k).sort();

  it('en has a non-empty namespace', () => {
    expect(enKeys.length).toBeGreaterThan(0);
  });

  it.each([
    ['ru', ru],
    ['kz', kz],
  ] as const)('%s carries the identical key set with non-empty strings', (_, messages) => {
    const entries = leaves(messages[ns]);
    expect(entries.map(([k]) => k).sort()).toEqual(enKeys);
    for (const [, v] of entries) expect(typeof v === 'string' && v.trim().length > 0).toBe(true);
  });
});
