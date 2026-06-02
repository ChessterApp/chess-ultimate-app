import { describe, it, expect } from 'vitest';
import {
  parseCsv,
  detectColumnMapping,
  mapRows,
  applyTierCap,
} from '../csv-importer';

describe('parseCsv', () => {
  it('splits simple comma-separated rows', () => {
    expect(parseCsv('a,b\n1,2')).toEqual([
      ['a', 'b'],
      ['1', '2'],
    ]);
  });

  it('handles quoted fields containing commas', () => {
    expect(parseCsv('name,note\n"Doe, Jane",hello')).toEqual([
      ['name', 'note'],
      ['Doe, Jane', 'hello'],
    ]);
  });

  it('handles escaped quotes', () => {
    expect(parseCsv('a\n"hello ""world"""')).toEqual([['a'], ['hello "world"']]);
  });

  it('strips blank lines', () => {
    expect(parseCsv('a\n\n\nb')).toEqual([['a'], ['b']]);
  });
});

describe('detectColumnMapping', () => {
  it('detects email by exact header', () => {
    const m = detectColumnMapping(['Email', 'Name']);
    expect(m.email).toBe(0);
    expect(m.first_name).toBe(1);
    expect(m.auto_detected).toBe(true);
  });

  it('is case- and space-insensitive', () => {
    const m = detectColumnMapping(['  e-mail  ', 'First Name', 'Last Name']);
    expect(m.email).toBe(0);
    expect(m.first_name).toBe(1);
    expect(m.last_name).toBe(2);
  });

  it('falls back to substring match for compound headers', () => {
    const m = detectColumnMapping(['student_email_address']);
    expect(m.email).toBe(0);
  });

  it('marks not auto_detected when no email column found', () => {
    const m = detectColumnMapping(['x', 'y']);
    expect(m.auto_detected).toBe(false);
    expect(m.email).toBeNull();
  });

  it('maps "Name" alone to first_name', () => {
    const m = detectColumnMapping(['Email', 'Name']);
    expect(m.first_name).toBe(1);
    expect(m.last_name).toBeNull();
  });
});

describe('mapRows', () => {
  const mapping = { email: 0, first_name: 1, last_name: 2, auto_detected: true };

  it('flags invalid emails', () => {
    const out = mapRows(
      [
        ['ok@example.com', 'A', 'B'],
        ['not-an-email', 'C'],
      ],
      mapping,
    );
    expect(out.accepted_count).toBe(1);
    expect(out.invalid_count).toBe(1);
    expect(out.rows[1].status).toBe('invalid');
  });

  it('dedupes case-insensitively', () => {
    const out = mapRows(
      [
        ['a@x.com', 'A'],
        ['A@X.COM', 'A2'],
      ],
      mapping,
    );
    expect(out.accepted_count).toBe(1);
    expect(out.duplicate_count).toBe(1);
    expect(out.rows[1].status).toBe('duplicate');
  });

  it('considers existing emails when deduping', () => {
    const out = mapRows([['existing@x.com', '']], mapping, ['EXISTING@x.com']);
    expect(out.rows[0].status).toBe('duplicate');
  });

  it('preserves first/last names', () => {
    const out = mapRows([['kid@x.com', 'Kid', 'Smith']], mapping);
    expect(out.rows[0].first_name).toBe('Kid');
    expect(out.rows[0].last_name).toBe('Smith');
  });
});

describe('applyTierCap', () => {
  const okRows = [
    { index: 0, email: 'a@x.com', status: 'ok' as const },
    { index: 1, email: 'b@x.com', status: 'ok' as const },
    { index: 2, email: 'c@x.com', status: 'ok' as const },
  ];

  it('returns all rows when seats unlimited', () => {
    const out = applyTierCap(okRows, null);
    expect(out.to_import).toHaveLength(3);
    expect(out.skipped_for_cap).toHaveLength(0);
  });

  it('caps to remaining seats', () => {
    const out = applyTierCap(okRows, 2);
    expect(out.to_import).toHaveLength(2);
    expect(out.skipped_for_cap).toHaveLength(1);
    expect(out.skipped_for_cap[0].email).toBe('c@x.com');
  });

  it('skips everything at zero seats', () => {
    const out = applyTierCap(okRows, 0);
    expect(out.to_import).toHaveLength(0);
    expect(out.skipped_for_cap).toHaveLength(3);
  });

  it('ignores invalid/duplicate rows in the cap math', () => {
    const mixed = [
      ...okRows,
      { index: 3, email: 'bad', status: 'invalid' as const },
      { index: 4, email: 'dup@x.com', status: 'duplicate' as const },
    ];
    const out = applyTierCap(mixed, 10);
    expect(out.to_import).toHaveLength(3);
    expect(out.skipped_for_cap).toHaveLength(0);
  });
});
