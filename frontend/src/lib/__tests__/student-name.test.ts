import { describe, it, expect } from 'vitest';
import { resolveStudentDisplayName } from '../student-name';

describe('resolveStudentDisplayName', () => {
  it('returns trimmed first_name when present', () => {
    expect(
      resolveStudentDisplayName({ first_name: 'Ali', full_name: 'Turabay Ali' }),
    ).toBe('Ali');
  });

  it('trims whitespace around first_name', () => {
    expect(resolveStudentDisplayName({ first_name: '  Aiman  ' })).toBe('Aiman');
  });

  it('falls back to first token of full_name when first_name is null', () => {
    expect(
      resolveStudentDisplayName({ first_name: null, full_name: 'Amir Ahmed' }),
    ).toBe('Amir');
  });

  it('falls back to first token of full_name when first_name is empty string', () => {
    expect(
      resolveStudentDisplayName({ first_name: '', full_name: 'Amir Ahmed' }),
    ).toBe('Amir');
  });

  it('falls back to first token of full_name when first_name is only whitespace', () => {
    expect(
      resolveStudentDisplayName({ first_name: '   ', full_name: 'Amir Ahmed' }),
    ).toBe('Amir');
  });

  it('handles Cyrillic full_name split on whitespace', () => {
    expect(
      resolveStudentDisplayName({
        first_name: null,
        full_name: 'Айман Каримова',
      }),
    ).toBe('Айман');
  });

  it('handles Cyrillic full_name with tab/newline whitespace', () => {
    expect(
      resolveStudentDisplayName({
        first_name: null,
        full_name: 'Айман\tКаримова',
      }),
    ).toBe('Айман');
  });

  it('returns first_name (Cyrillic) as-is when present', () => {
    expect(
      resolveStudentDisplayName({
        first_name: 'Айман',
        full_name: 'Айман Каримова',
      }),
    ).toBe('Айман');
  });

  it('returns null when both fields missing', () => {
    expect(resolveStudentDisplayName({})).toBeNull();
  });

  it('returns null when both fields empty strings', () => {
    expect(
      resolveStudentDisplayName({ first_name: '', full_name: '' }),
    ).toBeNull();
  });

  it('returns null when both fields are only whitespace', () => {
    expect(
      resolveStudentDisplayName({ first_name: '   ', full_name: '\t\n ' }),
    ).toBeNull();
  });

  it('returns null when student is null', () => {
    expect(resolveStudentDisplayName(null)).toBeNull();
  });

  it('returns null when student is undefined', () => {
    expect(resolveStudentDisplayName(undefined)).toBeNull();
  });

  it('never returns an empty string — always null instead', () => {
    const result = resolveStudentDisplayName({ first_name: '', full_name: '' });
    expect(result).toBeNull();
    expect(result).not.toBe('');
  });

  it('does not fall back to any email or username shape', () => {
    // Sanity: the helper does not accept email/clerk fields even at the type
    // level, so this simply confirms nothing weird happens on empties.
    expect(
      resolveStudentDisplayName({
        first_name: null,
        full_name: null,
      }),
    ).toBeNull();
  });
});
