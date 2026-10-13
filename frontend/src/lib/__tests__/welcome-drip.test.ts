import { beforeEach, describe, expect, it, vi } from 'vitest';

const upsert = vi.fn();
const from = vi.fn(() => ({ upsert }));
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: { from: (...a: unknown[]) => from(...(a as [])) },
}));

import { scheduleWelcomeDrip, welcomeLocale } from '@/lib/welcome-drip';

const NOW = new Date('2026-10-13T10:00:00.000Z');

const user = (over: Record<string, unknown> = {}) => ({
  id: 'user_1',
  email_addresses: [
    { id: 'e0', email_address: 'other@x.io' },
    { id: 'e1', email_address: 'Kid@X.io' },
  ],
  primary_email_address_id: 'e1',
  first_name: ' Aru ',
  unsafe_metadata: {},
  ...over,
});

beforeEach(() => {
  upsert.mockReset();
  upsert.mockResolvedValue({ error: null });
  from.mockClear();
});

describe('scheduleWelcomeDrip', () => {
  it('upserts 5 rows at day 0/1/3/5/7, ignoring duplicates', async () => {
    await scheduleWelcomeDrip(user(), NOW);
    expect(from).toHaveBeenCalledWith('welcome_emails');
    const [rows, opts] = upsert.mock.calls[0];
    expect(opts).toEqual({ onConflict: 'user_id,step', ignoreDuplicates: true });
    expect(rows.map((r: { step: number }) => r.step)).toEqual([1, 2, 3, 4, 5]);
    expect(rows.map((r: { scheduled_for: string }) => r.scheduled_for)).toEqual([
      '2026-10-13T10:00:00.000Z',
      '2026-10-14T10:00:00.000Z',
      '2026-10-16T10:00:00.000Z',
      '2026-10-18T10:00:00.000Z',
      '2026-10-20T10:00:00.000Z',
    ]);
    expect(rows[0]).toMatchObject({
      user_id: 'user_1',
      email: 'kid@x.io',
      first_name: 'Aru',
      locale: 'en',
    });
  });

  it('stores a null first_name when Clerk has none', async () => {
    await scheduleWelcomeDrip(user({ first_name: null }), NOW);
    expect(upsert.mock.calls[0][0][0].first_name).toBeNull();
  });

  it('skips invite / branch-token (school) signups', async () => {
    await scheduleWelcomeDrip(user({ unsafe_metadata: { inviteJwt: 'eyJ.jwt' } }), NOW);
    expect(upsert).not.toHaveBeenCalled();
  });

  it('skips users with no email', async () => {
    await scheduleWelcomeDrip(user({ email_addresses: [] }), NOW);
    expect(upsert).not.toHaveBeenCalled();
  });

  it('swallows a DB error result', async () => {
    upsert.mockResolvedValue({ error: { message: 'boom' } });
    await expect(scheduleWelcomeDrip(user(), NOW)).resolves.toBeUndefined();
  });

  it('swallows a thrown DB error', async () => {
    upsert.mockRejectedValue(new Error('network'));
    await expect(scheduleWelcomeDrip(user(), NOW)).resolves.toBeUndefined();
  });
});

describe('welcomeLocale', () => {
  it('maps the app locale (kz → kk) from preferred_locale', () => {
    expect(welcomeLocale({ unsafe_metadata: { preferred_locale: 'kz' } })).toBe('kk');
    expect(welcomeLocale({ unsafe_metadata: { preferred_locale: 'ru' } })).toBe('ru');
    expect(welcomeLocale({ public_metadata: { locale: 'en' } })).toBe('en');
  });

  it('falls back to en for missing or unknown values', () => {
    expect(welcomeLocale({})).toBe('en');
    expect(welcomeLocale({ unsafe_metadata: { preferred_locale: 'de' } })).toBe('en');
  });
});
