'use client';

import { useEffect } from 'react';
import { useToast } from '@/components/ToastProvider';
import { initErrorReporting, reportError } from '@/lib/errorReporter';

export default function UnhandledErrorCatcher() {
  const { showToast } = useToast();

  useEffect(() => {
    // Initialize error reporting (logs to /api/errors)
    initErrorReporting();

    const handler = (event: PromiseRejectionEvent) => {
      event.preventDefault();
      console.error('Unhandled rejection:', event.reason);
      reportError(
        event.reason instanceof Error ? event.reason : String(event.reason),
        'unhandledrejection'
      );
      showToast('An unexpected error occurred', 'error');
    };

    window.addEventListener('unhandledrejection', handler);
    return () => window.removeEventListener('unhandledrejection', handler);
  }, [showToast]);

  return null;
}
