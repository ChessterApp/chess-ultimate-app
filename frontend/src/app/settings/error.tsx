'use client';

import { useEffect } from 'react';
import { reportError } from '@/lib/errorReporter';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Settings error:', error);
    reportError(error, 'component', { page: 'settings', digest: error.digest });
  }, [error]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-b from-purple-50 to-white p-4">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-4">⚙️</div>
        <h2 className="text-2xl font-bold text-gray-800 mb-2">Settings error</h2>
        <p className="text-gray-500 mb-6">
          Couldn&apos;t load your settings. Let&apos;s try that again.
        </p>
        <div className="space-y-3">
          <button
            onClick={reset}
            className="w-full px-6 py-3 bg-purple-600 text-white rounded-xl font-semibold hover:bg-purple-700 transition-colors"
          >
            Try Again
          </button>
          <a
            href="/profile"
            className="block w-full px-6 py-3 bg-gray-100 text-gray-700 rounded-xl font-semibold hover:bg-gray-200 transition-colors"
          >
            Back to Profile
          </a>
        </div>
      </div>
    </div>
  );
}
