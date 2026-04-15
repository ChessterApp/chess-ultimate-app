'use client';

import { useState, useEffect, useCallback } from 'react';
import { usePowerSyncContext } from '@/lib/powersync/PowerSyncProvider';
import { SYNC_INDICATOR, POWERSYNC_ENABLED } from '@/lib/feature-flags';

type SyncState = 'syncing' | 'synced' | 'offline';

/**
 * Sync status indicator — small dot in the bottom-right corner.
 * Green pulse = syncing, solid green = synced, gray = offline.
 * Click to expand: last sync time, items pending, connection status.
 */
export default function SyncIndicator() {
  if (!SYNC_INDICATOR || !POWERSYNC_ENABLED) {
    return null;
  }

  return <SyncIndicatorInner />;
}

function SyncIndicatorInner() {
  const { database, isReady } = usePowerSyncContext();
  const [syncState, setSyncState] = useState<SyncState>('synced');
  const [expanded, setExpanded] = useState(false);
  const [lastSyncTime, setLastSyncTime] = useState<Date | null>(null);
  const [pendingUploads, setPendingUploads] = useState(0);
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );

  // Track online/offline
  useEffect(() => {
    const goOnline = () => setIsOnline(true);
    const goOffline = () => setIsOnline(false);
    window.addEventListener('online', goOnline);
    window.addEventListener('offline', goOffline);
    return () => {
      window.removeEventListener('online', goOnline);
      window.removeEventListener('offline', goOffline);
    };
  }, []);

  // Subscribe to PowerSync status changes reactively
  useEffect(() => {
    if (!database || !isReady) return;

    const updateFromStatus = () => {
      if (!isOnline) {
        setSyncState('offline');
        return;
      }

      const status = database.currentStatus;
      if (status?.dataFlowStatus) {
        const { downloading, uploading } = status.dataFlowStatus;
        if (downloading || uploading) {
          setSyncState('syncing');
        } else {
          setSyncState('synced');
          setLastSyncTime(new Date());
        }
      }
    };

    updateFromStatus();

    // Use registerListener for reactive updates instead of polling
    const dispose = database.registerListener?.({
      statusChanged: updateFromStatus,
    });

    // Fallback to polling if registerListener is not available
    if (!dispose) {
      const interval = setInterval(updateFromStatus, 2000);
      return () => clearInterval(interval);
    }

    return () => dispose?.();
  }, [database, isReady, isOnline]);

  // Check pending uploads
  useEffect(() => {
    if (!database || !isReady) return;

    const checkPending = async () => {
      try {
        const tx = await database.getNextCrudTransaction();
        setPendingUploads(tx ? tx.crud.length : 0);
      } catch {
        setPendingUploads(0);
      }
    };

    checkPending();
    const interval = setInterval(checkPending, 5000);
    return () => clearInterval(interval);
  }, [database, isReady]);

  const handleClick = useCallback(() => {
    setExpanded((prev) => !prev);
  }, []);

  const dotClasses = {
    syncing: 'bg-green-500 animate-pulse shadow-green-500/50',
    synced: 'bg-green-500 shadow-green-500/30',
    offline: 'bg-gray-400 shadow-gray-400/30',
  };

  const stateLabels: Record<SyncState, string> = {
    syncing: 'Syncing...',
    synced: 'Synced',
    offline: 'Offline',
  };

  const formatTime = (date: Date | null) => {
    if (!date) return 'Never';
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    if (diffSecs < 10) return 'Just now';
    if (diffSecs < 60) return `${diffSecs}s ago`;
    const diffMins = Math.floor(diffSecs / 60);
    if (diffMins < 60) return `${diffMins}m ago`;
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="fixed bottom-4 right-4 z-40 md:bottom-6 md:right-6">
      {expanded && (
        <div
          className="mb-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 p-3 text-xs min-w-[180px]"
          data-testid="sync-panel"
        >
          <div className="flex items-center gap-2 mb-2">
            <div className={`w-2 h-2 rounded-full ${dotClasses[syncState]}`} />
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {stateLabels[syncState]}
            </span>
          </div>
          <div className="space-y-1 text-gray-600 dark:text-gray-400">
            <div className="flex justify-between">
              <span>Last sync:</span>
              <span>{formatTime(lastSyncTime)}</span>
            </div>
            <div className="flex justify-between">
              <span>Pending:</span>
              <span>{pendingUploads} item{pendingUploads !== 1 ? 's' : ''}</span>
            </div>
            <div className="flex justify-between">
              <span>Connection:</span>
              <span>{isOnline ? 'Online' : 'Offline'}</span>
            </div>
          </div>
        </div>
      )}
      <button
        onClick={handleClick}
        className="block ml-auto"
        aria-label={`Sync status: ${stateLabels[syncState]}`}
        data-testid="sync-indicator"
      >
        <div
          className={`w-2.5 h-2.5 rounded-full shadow-sm ${dotClasses[syncState]}`}
        />
      </button>
    </div>
  );
}
