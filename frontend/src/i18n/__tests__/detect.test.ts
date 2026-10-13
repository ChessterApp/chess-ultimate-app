import { describe, it, expect } from 'vitest';
import { localeFromAcceptLanguage, resolveLocale } from '../detect';

describe('localeFromAcceptLanguage', () => {
  it.each([
    ['kk-KZ,ru;q=0.8', 'kz'],
    ['ru-RU', 'ru'],
    ['en-US,en;q=0.9', 'ru'],
    ['en;q=0.9,kk;q=0.8', 'kz'],
    ['ru;q=0.5,kk;q=0.9', 'kz'],
    ['kz', 'kz'],
    ['ru;q=0.9,kk;q=0.9', 'ru'],
    ['kk;q=0,ru;q=0.5', 'ru'],
  ])('%s → %s', (header, expected) => {
    expect(localeFromAcceptLanguage(header)).toBe(expected);
  });

  it.each([[''], [undefined], [null], ['garbage'], [';;,,q=abc'], ['*']])(
    'falls back to ru for %j',
    (header) => {
      expect(localeFromAcceptLanguage(header)).toBe('ru');
    },
  );
});

describe('resolveLocale', () => {
  it('a valid cookie wins over the header', () => {
    expect(resolveLocale('kz', 'ru-RU')).toBe('kz');
    expect(resolveLocale('en', 'kk-KZ')).toBe('en');
  });

  it('ignores an invalid cookie and uses the header', () => {
    expect(resolveLocale('xx', 'kk-KZ')).toBe('kz');
    expect(resolveLocale('xx', 'en-US')).toBe('ru');
  });

  it('uses the header when no cookie is saved', () => {
    expect(resolveLocale(undefined, 'kk')).toBe('kz');
    expect(resolveLocale(undefined, undefined)).toBe('ru');
  });
});
