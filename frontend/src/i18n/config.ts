export const locales = ['en', 'ru', 'kz'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'en';

export const localeNames: Record<Locale, string> = {
  en: 'English',
  ru: 'Русский',
  kz: 'Қазақша'
};

export const localeFlags: Record<Locale, string> = {
  en: '🇺🇸',
  ru: '🇷🇺',
  kz: '🇰🇿'
};
