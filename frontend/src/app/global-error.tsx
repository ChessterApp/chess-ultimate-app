'use client';

import { useEffect } from 'react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Inline error reporting — can't use imports since CSS/JS may be broken
    try {
      fetch('/api/errors', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ errors: [{
          message: error.message,
          stack: error.stack?.substring(0, 2000),
          url: window.location.href,
          timestamp: new Date().toISOString(),
          type: 'component',
          meta: { page: 'global-error', digest: error.digest },
        }] }),
        keepalive: true,
      }).catch(() => {});
    } catch { /* best effort */ }
  }, [error]);

  return (
    <html>
      <body>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui, sans-serif', padding: '1rem', background: 'linear-gradient(to bottom, var(--primary-light, #EDE9FE), var(--surface-card, #FFFFFF))' }}>
          <div style={{ textAlign: 'center', maxWidth: '400px' }}>
            <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>♞</div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--text-primary, #18181B)', marginBottom: '0.5rem' }}>Something went wrong</h2>
            <p style={{ color: 'var(--text-secondary, #52525B)', marginBottom: '1.5rem' }}>We encountered an unexpected error. Please try refreshing the page.</p>
            <button
              onClick={reset}
              style={{ padding: '0.75rem 1.5rem', backgroundColor: 'var(--primary, #8B5CF6)', color: 'var(--text-on-primary, #FFFFFF)', border: 'none', borderRadius: '0.75rem', fontWeight: '600', cursor: 'pointer', fontSize: '1rem' }}
            >
              Try Again
            </button>
          </div>
        </div>
      </body>
    </html>
  );
}
