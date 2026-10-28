import { defaultLocale, locales, type Locale } from './config';

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (locales as readonly string[]).includes(value);
}

/**
 * Map an `Accept-Language` header to an app locale. Locked rule: Kazakh →
 * `kz`, Russian → `ru`, anything else (including English) → `ru`. Tags are
 * ranked by q-weight (stable for ties, so header order breaks them); the first
 * Kazakh or Russian tag wins.
 */
export function localeFromAcceptLanguage(header: string | null | undefined): Locale {
  if (!header) return defaultLocale;
  const ranked = header
    .split(',')
    .map((part, index) => {
      const [tag, ...params] = part.trim().split(';');
      const qParam = params.map((p) => p.trim()).find((p) => p.startsWith('q='));
      const q = qParam ? Number(qParam.slice(2)) : 1;
      return { primary: tag.trim().toLowerCase().split('-')[0], q: Number.isFinite(q) ? q : 0, index };
    })
    .filter((t) => t.primary && t.q > 0)
    .sort((a, b) => b.q - a.q || a.index - b.index);

  for (const { primary } of ranked) {
    if (primary === 'kk' || primary === 'kz') return 'kz';
    if (primary === 'ru') return 'ru';
  }
  return defaultLocale;
}

/** Saved `NEXT_LOCALE` cookie (if valid) → `Accept-Language` → `ru`. */
export function resolveLocale(
  cookieValue: string | null | undefined,
  acceptLanguage: string | null | undefined,
): Locale {
  if (isLocale(cookieValue)) return cookieValue;
  return localeFromAcceptLanguage(acceptLanguage);
}

/**
 * The locale of an incoming request, resolved as the page resolves it (i18n/request.ts). The coach proxies
 * took the cookie or 'ru', so a Kazakh browser that never used the switcher got Russian replies under a
 * Kazakh interface (seam audit 28.10).
 */
export function requestLocale(request: {
  cookies?: { get(name: string): { value: string } | undefined };
  headers?: { get(name: string): string | null };
}): Locale {
  return resolveLocale(request.cookies?.get('NEXT_LOCALE')?.value, request.headers?.get('accept-language'));
}
