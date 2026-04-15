'use client';

import { useState, useEffect } from 'react';
import { usePowerSyncContext } from '@/lib/powersync/PowerSyncProvider';
import { INSTANT_LOADING, POWERSYNC_ENABLED } from '@/lib/feature-flags';

/**
 * Subtle sync indicator — small dot in the bottom-right corner that pulses
 * when PowerSync is actively syncing in the background. Invisible when idle.
 */
export default function SyncIndicator() {
  if (!INSTANT_LOADING || !POWERSYNC_ENABLED) {
    return null;
  }

  return <SyncIndicatorInner />;
}

function SyncIndicatorInner() {
  const { database, isReady } = usePowerSyncContext();
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(() => {
    if (!database || !isReady) return;

    const checkStatus = () => {
      const status = database.currentStatus;
      if (status?.dataFlowStatus) {
        const { downloading, uploading } = status.dataFlowStatus;
        setIsSyncing(!!(downloading || uploading));
      }
    };

    // Check immediately
    checkStatus();

    // Poll sync status (PowerSync doesn't expose a reactive status listener easily)
    const interval = setInterval(checkStatus, 2000);

    return () => clearInterval(interval);
  }, [database, isReady]);

  if (!isSyncing) return null;

  return (
    <div
      className="fixed bottom-4 right-4 z-40 md:bottom-6 md:right-6"
      title="Syncing..."
    >
      <div className="w-2.5 h-2.5 rounded-full bg-purple-500 animate-pulse shadow-sm shadow-purple-500/50" />
    </div>
  );
}
