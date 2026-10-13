#!/usr/bin/env node
/**
 * Read-only live check: every Clerk-id column in the database's public schema
 * must have a delete / nullify / keep decision in src/lib/user-data-manifest.ts
 * (the source of truth for public.delete_user_data, migration 053).
 *
 * Usage (from frontend/):
 *   SUPABASE_DB_URL=postgres://... node scripts/check-user-data-coverage.mjs
 *
 * Skips (exit 0) when SUPABASE_DB_URL is unset. Exits 1 on any uncovered column.
 * Queries information_schema via psql in a read-only transaction — NO writes.
 * Imports the .ts manifest directly (Node >= 22.18 strips types natively).
 */
import { execFileSync } from 'node:child_process';
import { isUserIdColumn, uncoveredUserIdColumns } from '../src/lib/user-data-manifest.ts';

const dbUrl = process.env.SUPABASE_DB_URL;
if (!dbUrl) {
  console.log('SUPABASE_DB_URL not set — skipping live user-data coverage check.');
  process.exit(0);
}

const sql = `
  select c.table_name, c.column_name
  from information_schema.columns c
  join information_schema.tables t
    on t.table_schema = c.table_schema and t.table_name = c.table_name
  where c.table_schema = 'public' and t.table_type = 'BASE TABLE'
  order by 1, 2`;

const out = execFileSync('psql', [dbUrl, '-At', '-F', '\t', '-c', sql], {
  encoding: 'utf8',
  env: { ...process.env, PGOPTIONS: '-c default_transaction_read_only=on' },
});

const columns = out
  .split('\n')
  .filter(Boolean)
  .map((line) => {
    const [table, column] = line.split('\t');
    return { table, column };
  });

const userIdColumns = columns.filter((c) => isUserIdColumn(c.column));
const uncovered = uncoveredUserIdColumns(columns);

console.log(`Checked ${userIdColumns.length} user-id columns across ${new Set(columns.map((c) => c.table)).size} tables.`);
if (uncovered.length > 0) {
  console.error('Uncovered user-id columns (add a decision to src/lib/user-data-manifest.ts + migration):');
  for (const key of uncovered) console.error(`  - ${key}`);
  process.exit(1);
}
console.log('All user-id columns are covered.');
