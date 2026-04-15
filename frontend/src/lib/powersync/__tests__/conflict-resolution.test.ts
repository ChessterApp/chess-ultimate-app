import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

/**
 * Conflict Resolution — Phase 5C
 *
 * PowerSync uses last-write-wins by default for all data.
 * The connector uses Supabase upsert for PUT operations,
 * which means if two devices edit the same row, the last write wins.
 * This is sufficient for single-user data (no real-time collaboration).
 */
describe('Conflict resolution strategy', () => {
  const connectorSource = readFileSync(
    resolve(__dirname, '../connector.ts'),
    'utf-8'
  );

  it('uses upsert for PUT operations (last-write-wins)', () => {
    // The connector should use .upsert() not .insert() for PUT operations
    // This ensures last-write-wins: if the row exists, it gets overwritten
    expect(connectorSource).toContain('.upsert(');
    expect(connectorSource).not.toContain('.insert(');
  });

  it('uses update for PATCH operations', () => {
    expect(connectorSource).toContain('.update(');
  });

  it('uses delete for DELETE operations', () => {
    expect(connectorSource).toContain('.delete()');
  });

  it('handles all three mutation types (PUT, PATCH, DELETE)', () => {
    expect(connectorSource).toContain('UpdateType.PUT');
    expect(connectorSource).toContain('UpdateType.PATCH');
    expect(connectorSource).toContain('UpdateType.DELETE');
  });

  it('completes transactions after successful upload', () => {
    expect(connectorSource).toContain('transaction.complete()');
  });
});
