'use client';

import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { POWERSYNC_ENABLED } from '@/lib/feature-flags';
import type { AbstractPowerSyncDatabase } from '@powersync/web';

interface PowerSyncContextValue {
  database: AbstractPowerSyncDatabase | null;
  isReady: boolean;
}

const PowerSyncCtx = createContext<PowerSyncContextValue>({
  database: null,
  isReady: false,
});

export const usePowerSyncContext = () => useContext(PowerSyncCtx);

/**
 * Initializes PowerSync with OPFS backend, connects via Clerk JWT,
 * and provides the database to the component tree via both:
 * - Our own context (for SyncIndicator/SyncBoundary)
 * - @powersync/react's PowerSyncContext (so useQuery() works)
 *
 * Only activates when POWERSYNC_ENABLED feature flag is true.
 * Otherwise renders children unchanged with no overhead.
 */
export function PowerSyncProvider({ children }: { children: React.ReactNode }) {
  if (!POWERSYNC_ENABLED) {
    return <>{children}</>;
  }

  return <PowerSyncInner>{children}</PowerSyncInner>;
}

function PowerSyncInner({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth();
  const [ctx, setCtx] = useState<PowerSyncContextValue>({
    database: null,
    isReady: false,
  });
  // Store the PowerSyncContext component once dynamically imported
  const [PSContext, setPSContext] = useState<React.Context<any> | null>(null);
  const initRef = useRef(false);

  useEffect(() => {
    if (initRef.current) return;
    initRef.current = true;

    let db: AbstractPowerSyncDatabase | undefined;

    async function init() {
      // Dynamic imports keep PowerSync out of the server bundle
      const { PowerSyncDatabase } = await import('@powersync/web');
      const { PowerSyncContext } = await import('@powersync/react');
      const { AppSchema } = await import('./schema');
      const { SupabasePowerSyncConnector } = await import('./connector');

      db = new PowerSyncDatabase({
        schema: AppSchema,
        database: { dbFilename: 'chesster-powersync.db' },
        flags: { disableSSRWarning: true },
      });

      const connector = new SupabasePowerSyncConnector(getToken);
      await db.connect(connector);

      console.log('[PowerSync] Connected — sync status:', db.currentStatus?.dataFlowStatus);

      setPSContext(PowerSyncContext as unknown as React.Context<any>);
      setCtx({
        database: db,
        isReady: true,
      });
    }

    init().catch((err) => {
      console.error('[PowerSync] Init failed:', err);
    });

    return () => {
      db?.disconnect();
    };
  }, [getToken]);

  // Wrap children with @powersync/react's context so useQuery() works
  let content = <>{children}</>;
  if (PSContext && ctx.database) {
    content = (
      <PSContext.Provider value={ctx.database}>
        {children}
      </PSContext.Provider>
    );
  }

  return (
    <PowerSyncCtx.Provider value={ctx}>
      {content}
    </PowerSyncCtx.Provider>
  );
}
