/**
 * Lightweight client-side error reporter.
 * Batches errors and sends them to /api/errors every 10 seconds (or on page unload).
 * No external service required — logs to server-side file.
 */

interface ErrorReport {
  message: string;
  stack?: string;
  url: string;
  timestamp: string;
  userAgent: string;
  type: 'error' | 'unhandledrejection' | 'api' | 'component';
  meta?: Record<string, unknown>;
}

let errorQueue: ErrorReport[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function createReport(
  message: string,
  type: ErrorReport['type'],
  stack?: string,
  meta?: Record<string, unknown>
): ErrorReport {
  return {
    message: message.substring(0, 1000),
    stack: stack?.substring(0, 2000),
    url: typeof window !== 'undefined' ? window.location.href : '',
    timestamp: new Date().toISOString(),
    userAgent: typeof navigator !== 'undefined' ? navigator.userAgent.substring(0, 200) : '',
    type,
    meta,
  };
}

function scheduleFlush() {
  if (flushTimer) return;
  flushTimer = setTimeout(flush, 10000);
}

async function flush() {
  flushTimer = null;
  if (errorQueue.length === 0) return;

  const batch = errorQueue.splice(0, 20); // max 20 per flush
  try {
    await fetch('/api/errors', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ errors: batch }),
      keepalive: true, // survives page unload
    });
  } catch {
    // If reporting fails, don't re-queue (avoid loops)
  }
}

/** Report an error from anywhere in the app */
export function reportError(
  error: Error | string,
  type: ErrorReport['type'] = 'error',
  meta?: Record<string, unknown>
) {
  const message = error instanceof Error ? error.message : error;
  const stack = error instanceof Error ? error.stack : undefined;
  errorQueue.push(createReport(message, type, stack, meta));
  scheduleFlush();
}

/** Report an API error with status code */
export function reportApiError(url: string, status: number, message: string) {
  reportError(message, 'api', { apiUrl: url, status });
}

/** Initialize global error listeners — call once in app root */
export function initErrorReporting() {
  if (typeof window === 'undefined') return;

  window.addEventListener('error', (event) => {
    reportError(
      event.error || event.message,
      'error',
      { filename: event.filename, lineno: event.lineno, colno: event.colno }
    );
  });

  window.addEventListener('unhandledrejection', (event) => {
    const error = event.reason;
    reportError(
      error instanceof Error ? error : String(error),
      'unhandledrejection'
    );
  });

  // Flush on page unload
  window.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      flush();
    }
  });
}
