'use client';

/**
 * TokenRedirect — client-side bounce from `/g/u/<token>` to
 * `/database?gu=<token>`.
 *
 * Mirrors the master-game `GameRedirect`: messenger crawlers don't run JS, so
 * the `/g/u/` server response carries the Open Graph tags (see page.tsx). Real
 * browsers run this and get sent to /database, where the recipient is gated
 * behind sign-in before the shared game is fetched.
 */
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function TokenRedirect({
  token,
  openingLabel,
  manualLabel,
}: {
  token: string;
  openingLabel: string;
  manualLabel: string;
}) {
  const router = useRouter();
  const href = `/database?gu=${encodeURIComponent(token)}`;

  useEffect(() => {
    router.replace(href);
  }, [router, href]);

  return (
    <main
      style={{
        minHeight: '60vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 12,
        fontFamily: 'system-ui, sans-serif',
        textAlign: 'center',
        padding: 24,
      }}
    >
      <p style={{ fontSize: 18, color: '#444' }}>{openingLabel}</p>
      <a href={href} style={{ color: '#8209a3', fontWeight: 600 }}>
        {manualLabel}
      </a>
    </main>
  );
}
