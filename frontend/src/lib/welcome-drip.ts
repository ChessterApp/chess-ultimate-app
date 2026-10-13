/**
 * Welcome drip scheduling (P4 — sent via Resend). On Clerk
 * `user.created` we write the five `welcome_emails` rows; the Flask cron
 * (`flask welcome-emails send-due`) sends them. Best-effort: never throws.
 */
import { supabaseAdmin } from '@/lib/supabase-admin';

export type WelcomeLocale = 'en' | 'ru' | 'kk';

/** Day offset of each step from signup. */
export const STEP_OFFSET_DAYS = [0, 1, 3, 5, 7] as const;

const DAY_MS = 24 * 60 * 60 * 1000;

type WelcomeUserData = {
  id?: string;
  email_addresses?: Array<{ id: string; email_address: string }>;
  primary_email_address_id?: string | null;
  first_name?: string | null;
  unsafe_metadata?: Record<string, unknown> | null;
  public_metadata?: Record<string, unknown> | null;
};

/** Lower-cased, so opt-outs (`email_opt_outs.email`) match by equality. */
function primaryEmail(data: WelcomeUserData): string | null {
  const emails = data.email_addresses || [];
  const hit = emails.find((e) => e?.id === data.primary_email_address_id) || emails[0];
  return hit?.email_address?.trim().toLowerCase() || null;
}

/**
 * UI locale saved by the language switcher / sign-up page as
 * `preferred_locale` (app codes en|ru|kz). The app's `kz` is `kk` in email.
 */
export function welcomeLocale(data: WelcomeUserData): WelcomeLocale {
  for (const meta of [data.unsafe_metadata, data.public_metadata]) {
    const raw = meta?.preferred_locale ?? meta?.locale;
    if (typeof raw !== 'string') continue;
    const code = raw.toLowerCase();
    if (code === 'kz' || code === 'kk') return 'kk';
    if (code === 'ru' || code === 'en') return code;
  }
  return 'en';
}

/** School students (CE invite / branch-token signups) get no welcome drip. */
function isSchoolSignup(data: WelcomeUserData): boolean {
  const jwt = (data.unsafe_metadata || {})['inviteJwt'];
  return typeof jwt === 'string' && jwt.length > 0;
}

export async function scheduleWelcomeDrip(data: WelcomeUserData, now = new Date()): Promise<void> {
  try {
    const email = primaryEmail(data);
    if (!data.id || !email) {
      console.warn('[welcome-drip] no user id or primary email, skipping');
      return;
    }
    if (isSchoolSignup(data)) return;

    const locale = welcomeLocale(data);
    const firstName = (data.first_name || '').trim() || null;
    const rows = STEP_OFFSET_DAYS.map((days, i) => ({
      user_id: data.id,
      email,
      first_name: firstName,
      locale,
      step: i + 1,
      scheduled_for: new Date(now.getTime() + days * DAY_MS).toISOString(),
    }));
    const { error } = await supabaseAdmin
      .from('welcome_emails')
      .upsert(rows, { onConflict: 'user_id,step', ignoreDuplicates: true });
    if (error) console.error('[welcome-drip] schedule failed:', error.message);
  } catch (err) {
    console.error('[welcome-drip] schedule failed:', err);
  }
}
