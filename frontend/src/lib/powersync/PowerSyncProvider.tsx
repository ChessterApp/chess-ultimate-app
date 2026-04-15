'use client';

import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from '@clerk/nextjs';
import { POWERSYNC_ENABLED } from '@/lib/feature-flags';
import type { PowerSyncCollections } from './collections';
import type { AbstractPowerSyncDatabase } from '@powersync/web';

interface PowerSyncContextValue {
  database: AbstractPowerSyncDatabase | null;
  collections: PowerSyncCollections | null;
  isReady: boolean;
}

const PowerSyncCtx = createContext<PowerSyncContextValue>({
  database: null,
  collections: null,
  isReady: false,
});

export const usePowerSyncContext = () => useContext(PowerSyncCtx);

/**
 * Initializes PowerSync with OPFS backend, connects via Clerk JWT,
 * and provides TanStack DB collections to the component tree.
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
    collections: null,
    isReady: false,
  });
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
      const { createPowerSyncCollections } = await import('./collections');

      db = new PowerSyncDatabase({
        schema: AppSchema,
        database: { dbFilename: 'chesster-powersync.db' },
      });

      const connector = new SupabasePowerSyncConnector(getToken);
      await db.connect(connector);

      const collections = createPowerSyncCollections(db);

      console.log('[PowerSync] Connected — sync status:', db.currentStatus?.dataFlowStatus);

      setCtx({
        database: db,
        collections,
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

  return (
    <PowerSyncCtx.Provider value={ctx}>
      {children}
    </PowerSyncCtx.Provider>
  );
}
