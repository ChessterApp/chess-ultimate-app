'use client';

/**
 * GameRedirect — client-side bounce from `/g/<slug>` to `/database?g=<slug>`.
 *
 * Messenger crawlers (WhatsApp/Telegram) don't execute JS, so the `/g/` server
 * response carries the Open Graph tags (see page.tsx). Real browsers run this
 * and get sent on to /database, where Phase 1 logic opens the game (with the
 * sign-in gate). A visible "Opening game…" fallback + manual link covers the
 * no-JS / slow case.
 */
import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function GameRedirect({
  slug,
  openingLabel,
  manualLabel,
}: {
  slug: string;
  openingLabel: string;
  manualLabel: string;
}) {
  const router = useRouter();
  const href = `/database?g=${encodeURIComponent(slug)}`;

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
