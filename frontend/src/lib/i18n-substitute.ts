// Recursively replaces the literal token `{appName}` inside string values of a
// messages tree with the resolved tenant brand name. Done at request-config
// time so both server-side `getTranslations` and client-side `useTranslations`
// see the substituted text — next-intl v4 dropped `defaultTranslationValues`,
// so this is how we keep one source of truth for the tenant brand placeholder.

export const APP_NAME_TOKEN = '{appName}';

export function substituteAppName<T>(value: T, appName: string): T {
  if (typeof value === 'string') {
    return value.split(APP_NAME_TOKEN).join(appName) as unknown as T;
  }
  if (Array.isArray(value)) {
    return value.map(v => substituteAppName(v, appName)) as unknown as T;
  }
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = substituteAppName(v, appName);
    }
    return out as unknown as T;
  }
  return value;
}
