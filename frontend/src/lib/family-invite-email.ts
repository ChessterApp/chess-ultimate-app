/**
 * "Join family" invite email — best-effort Resend delivery for the cross-branch
 * / online→branch family-link consent flow.
 *
 * Mirrors the backend's transactional-email pattern (`services/email.py`): it
 * POSTs the Resend HTTP API directly and NEVER throws — a failed or
 * unconfigured send returns `false` so the invite row is still created and the
 * caller can surface the accept link another way. `RESEND_API_KEY` is read on
 * each call so tests can stub the env without re-importing.
 */
import 'server-only';

const RESEND_API_URL = 'https://api.resend.com/emails';
const DEFAULT_FROM = process.env.RESEND_INVITE_FROM || 'invites@chesster.io';

/** Base URL the accept link is built against (Chess Empire brand). */
export function familyInviteBaseUrl(): string {
  return (
    process.env.NEXT_PUBLIC_CE_APP_URL ||
    process.env.NEXT_PUBLIC_APP_URL ||
    'https://chess-empire.chesster.io'
  ).replace(/\/$/, '');
}

/** The page the target lands on to accept a family invite. */
export function familyInviteAcceptUrl(token: string): string {
  return `${familyInviteBaseUrl()}/family/join/${encodeURIComponent(token)}`;
}

function renderHtml(inviterName: string, acceptUrl: string): string {
  const who = inviterName || 'A Chess Empire family member';
  return `<!doctype html>
<html><body style="font-family:Inter,Arial,sans-serif;background:#f8fafc;padding:24px">
  <table cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;margin:0 auto;background:#fff;border-radius:12px;padding:32px">
    <tr><td>
      <h1 style="font-size:22px;margin:0 0 12px 0;color:#0f172a">${who} wants to add you to their Chess Empire family.</h1>
      <p style="font-size:15px;line-height:1.5;color:#334155">
        Joining a family lets you register each other for tournaments. You'll only be linked once you accept — nothing happens until you click below.
      </p>
      <p style="margin:24px 0">
        <a href="${acceptUrl}"
           style="display:inline-block;background:#2563eb;color:#fff;text-decoration:none;
                  padding:12px 20px;border-radius:8px;font-weight:600">
          Join family
        </a>
      </p>
      <p style="font-size:13px;color:#64748b">If the button doesn't work, copy this link:<br/>
        <a href="${acceptUrl}" style="color:#2563eb;word-break:break-all">${acceptUrl}</a></p>
      <p style="font-size:13px;color:#94a3b8">If you didn't expect this, you can safely ignore this email.</p>
    </td></tr>
  </table>
</body></html>`;
}

/**
 * Send a "join family" email. Returns true on send-success, false on any
 * failure (including a missing API key). Never throws.
 */
export async function sendFamilyInviteEmail(args: {
  toEmail: string;
  inviterName: string;
  acceptUrl: string;
}): Promise<boolean> {
  const apiKey = process.env.RESEND_API_KEY;
  if (!apiKey) {
    console.warn('[family-invite-email] RESEND_API_KEY not configured; skipping send');
    return false;
  }
  const who = args.inviterName || 'A Chess Empire family member';
  try {
    const res = await fetch(RESEND_API_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: DEFAULT_FROM,
        to: [args.toEmail],
        subject: `${who} invited you to their Chess Empire family`,
        html: renderHtml(args.inviterName, args.acceptUrl),
      }),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      console.error(`[family-invite-email] Resend HTTP ${res.status}: ${body.slice(0, 300)}`);
      return false;
    }
    return true;
  } catch (err) {
    console.error('[family-invite-email] send failed:', err);
    return false;
  }
}
