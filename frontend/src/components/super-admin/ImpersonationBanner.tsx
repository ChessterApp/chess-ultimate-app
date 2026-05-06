'use client';

import { useAuth } from '@clerk/nextjs';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

const COOKIE_NAME = 'chesster_impersonation';

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp('(?:^|; )' + name + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Renders a loud red banner across the top of every page when the super-admin
 * impersonation cookie is set. Clicking "Exit" clears the session.
 *
 * The cookie is mirrored from the backend's Set-Cookie response so we can read
 * it from JS — it is not a credential, just a UX signal. The actual write-block
 * lives server-side and trusts only its own cookie value.
 */
export default function ImpersonationBanner() {
  const router = useRouter();
  const { getToken } = useAuth();
  const [active, setActive] = useState(false);
  const [exiting, setExiting] = useState(false);

  useEffect(() => {
    const check = () => setActive(Boolean(readCookie(COOKIE_NAME)));
    check();
    // Re-check on focus and on storage events so navigations between pages
    // pick up cookie changes immediately.
    window.addEventListener('focus', check);
    window.addEventListener('storage', check);
    const interval = window.setInterval(check, 30_000);
    return () => {
      window.removeEventListener('focus', check);
      window.removeEventListener('storage', check);
      window.clearInterval(interval);
    };
  }, []);

  if (!active) return null;

  const exit = async () => {
    setExiting(true);
    try {
      const token = await getToken();
      await fetch('/api/super-admin/impersonation', {
        method: 'DELETE',
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
    } catch {
      // ignore — we still clear the cookie below
    }
    // Defensive client-side clear in case the cookie was set without HttpOnly
    // and the network call failed.
    document.cookie = `${COOKIE_NAME}=; path=/; max-age=0`;
    setActive(false);
    setExiting(false);
    router.push('/super-admin/users');
    router.refresh();
  };

  return (
    <div className="sticky top-0 z-[100] bg-red-600 text-white">
      <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2 text-sm">
        <span>
          <strong>Impersonating user (read-only).</strong> All write actions are blocked at the API.
        </span>
        <button
          type="button"
          onClick={exit}
          disabled={exiting}
          className="rounded bg-white/15 px-3 py-1 text-xs font-semibold hover:bg-white/25 disabled:opacity-60"
        >
          {exiting ? 'Exiting…' : 'Exit impersonation'}
        </button>
      </div>
    </div>
  );
}
