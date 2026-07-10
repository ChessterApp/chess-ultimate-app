import { getRequestConfig } from 'next-intl/server';
import { cookies, headers } from 'next/headers';

import { substituteAppName } from '@/lib/i18n-substitute';

export const locales = ['en', 'ru', 'kz'] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = 'ru';

async function resolveAppName(): Promise<string> {
  try {
    const h = await headers();
    const slug = h.get('x-org-slug');
    if (!slug) return 'Chesster';
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(
      `${backendUrl}/api/admin/organizations/by-slug/${slug}`,
      { next: { revalidate: 300 }, signal: AbortSignal.timeout(3000) },
    );
    if (!res.ok) return 'Chesster';
    const data = (await res.json()) as { name?: string };
    return data.name || 'Chesster';
  } catch {
    return 'Chesster';
  }
}

export default getRequestConfig(async () => {
  const cookieStore = await cookies();
  const locale = (cookieStore.get('NEXT_LOCALE')?.value as Locale) || defaultLocale;

  const rawMessages = (await import(`../../messages/${locale}.json`)).default;
  const appName = await resolveAppName();
  const messages = substituteAppName(rawMessages, appName);

  return {
    locale,
    messages,
  };
});
