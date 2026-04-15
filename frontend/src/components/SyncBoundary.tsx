'use client';

import { type ReactNode } from 'react';
import { usePowerSyncContext } from '@/lib/powersync/PowerSyncProvider';
import { INSTANT_LOADING, POWERSYNC_ENABLED } from '@/lib/feature-flags';

interface SyncBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

/**
 * SyncBoundary — shows content instantly from local cache, or a minimal
 * "syncing..." indicator only on the very first load (before PowerSync
 * has populated OPFS). On subsequent visits, children render immediately
 * from the local database with zero loading states.
 *
 * When INSTANT_LOADING is disabled, renders children unconditionally.
 */
export default function SyncBoundary({ children, fallback }: SyncBoundaryProps) {
  if (!INSTANT_LOADING || !POWERSYNC_ENABLED) {
    return <>{children}</>;
  }

  return <SyncBoundaryInner fallback={fallback}>{children}</SyncBoundaryInner>;
}

function SyncBoundaryInner({ children, fallback }: SyncBoundaryProps) {
  const { isReady } = usePowerSyncContext();

  // Check if we've ever completed an initial sync
  const hasEverSynced = typeof window !== 'undefined' &&
    localStorage.getItem('chesster:initial_sync_done') === 'true';

  // If we've synced before, render immediately (OPFS has data)
  if (hasEverSynced) {
    return <>{children}</>;
  }

  // First-ever load: wait for PowerSync to be ready
  if (!isReady) {
    return <>{fallback ?? <FirstLoadIndicator />}</>;
  }

  // Mark that initial sync has completed
  if (typeof window !== 'undefined') {
    localStorage.setItem('chesster:initial_sync_done', 'true');
  }

  return <>{children}</>;
}

function FirstLoadIndicator() {
  return (
    <div className="flex items-center justify-center min-h-[200px]">
      <div className="flex items-center gap-3 text-gray-400 dark:text-gray-500">
        <div className="w-2 h-2 rounded-full bg-purple-500 animate-pulse" />
        <span className="text-sm">Syncing your data...</span>
      </div>
    </div>
  );
}
