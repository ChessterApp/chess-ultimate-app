/**
 * Shared test helper: render an empire component under a real
 * NextIntlClientProvider seeded with a real catalog, plus a translator to
 * compute expected strings from the same catalog.
 */
import React from 'react';
import { render, type RenderOptions } from '@testing-library/react';
import { NextIntlClientProvider, createTranslator } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';

export const catalogs = { en, ru, kz } as const;
export type TestLocale = keyof typeof catalogs;

export function IntlWrapper({
  locale = 'en',
  children,
}: {
  locale?: TestLocale;
  children: React.ReactNode;
}) {
  return (
    <NextIntlClientProvider
      locale={locale}
      messages={catalogs[locale] as Record<string, unknown>}
      timeZone="UTC"
    >
      {children}
    </NextIntlClientProvider>
  );
}

export function renderIntl(
  ui: React.ReactElement,
  locale: TestLocale = 'en',
  options?: RenderOptions,
) {
  return render(<IntlWrapper locale={locale}>{ui}</IntlWrapper>, options);
}

export function tr(namespace: 'empire' | 'gamification', locale: TestLocale = 'en') {
  return createTranslator({
    locale,
    messages: catalogs[locale] as Record<string, unknown>,
    namespace,
  });
}
