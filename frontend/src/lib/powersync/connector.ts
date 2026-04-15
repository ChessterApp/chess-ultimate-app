import {
  AbstractPowerSyncDatabase,
  CrudEntry,
  PowerSyncBackendConnector,
  UpdateType,
} from '@powersync/web';
import { supabase } from '@/lib/supabase';

/** Function signature matching Clerk's getToken() */
export type GetTokenFn = () => Promise<string | null>;

/**
 * PowerSync backend connector that authenticates via Clerk JWT
 * and writes mutations back to Supabase.
 */
export class SupabasePowerSyncConnector implements PowerSyncBackendConnector {
  private getToken: GetTokenFn;

  constructor(getToken: GetTokenFn) {
    this.getToken = getToken;
  }

  async fetchCredentials() {
    const endpoint = process.env.NEXT_PUBLIC_POWERSYNC_URL;
    if (!endpoint) {
      throw new Error('NEXT_PUBLIC_POWERSYNC_URL is not configured');
    }

    const token = await this.getToken();
    if (!token) {
      return null;
    }

    return { endpoint, token };
  }

  async uploadData(database: AbstractPowerSyncDatabase): Promise<void> {
    const transaction = await database.getNextCrudTransaction();
    if (!transaction) return;

    try {
      for (const op of transaction.crud) {
        await this.applyOperation(op);
      }
      await transaction.complete();
    } catch (error) {
      console.error('[PowerSync] Upload failed:', error);
      throw error;
    }
  }

  private async applyOperation(op: CrudEntry): Promise<void> {
    const table = op.table;
    const id = op.id;

    switch (op.op) {
      case UpdateType.PUT: {
        const { data, error } = await supabase
          .from(table)
          .upsert({ id, ...op.opData });
        if (error) throw error;
        return;
      }
      case UpdateType.PATCH: {
        const { error } = await supabase
          .from(table)
          .update(op.opData!)
          .eq('id', id);
        if (error) throw error;
        return;
      }
      case UpdateType.DELETE: {
        const { error } = await supabase
          .from(table)
          .delete()
          .eq('id', id);
        if (error) throw error;
        return;
      }
    }
  }
}
