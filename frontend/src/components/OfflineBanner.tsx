'use client';

import { useState, useEffect, createContext, useContext } from 'react';
import { OFFLINE_MODE } from '@/lib/feature-flags';

interface OfflineContextValue {
  isOffline: boolean;
}

const OfflineCtx = createContext<OfflineContextValue>({ isOffline: false });

/**
 * Hook to check offline status from anywhere in the component tree.
 * Use this to disable mutation buttons when offline.
 */
export function useOfflineStatus() {
  return useContext(OfflineCtx);
}

/**
 * Offline banner + context provider.
 * Detects offline via navigator.onLine events.
 * Shows banner "You are offline — showing cached data".
 * Provides offline status to children via context.
 */
export default function OfflineBanner({ children }: { children?: React.ReactNode }) {
  const [isOffline, setIsOffline] = useState(false);

  useEffect(() => {
    const handleOffline = () => setIsOffline(true);
    const handleOnline = () => setIsOffline(false);

    setIsOffline(!navigator.onLine);

    window.addEventListener('offline', handleOffline);
    window.addEventListener('online', handleOnline);

    return () => {
      window.removeEventListener('offline', handleOffline);
      window.removeEventListener('online', handleOnline);
    };
  }, []);

  if (!OFFLINE_MODE) {
    // Feature disabled — still provide context but no banner
    return (
      <OfflineCtx.Provider value={{ isOffline }}>
        {children}
      </OfflineCtx.Provider>
    );
  }

  return (
    <OfflineCtx.Provider value={{ isOffline }}>
      {isOffline && (
        <div
          className="fixed top-0 left-0 right-0 z-[9999] bg-amber-600 text-white text-center py-2 px-4 text-sm font-medium shadow-lg"
          role="alert"
          data-testid="offline-banner"
        >
          You are offline — showing cached data
        </div>
      )}
      {children}
    </OfflineCtx.Provider>
  );
}

/**
 * Wrapper for mutation buttons that disables them when offline.
 * Shows a tooltip-like message when offline.
 */
export function OfflineGuard({
  children,
  fallback,
}: {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}) {
  const { isOffline } = useOfflineStatus();

  if (isOffline) {
    return (
      fallback ?? (
        <span className="text-gray-400 text-sm" data-testid="offline-guard">
          Reconnect to save changes
        </span>
      )
    );
  }

  return <>{children}</>;
}
