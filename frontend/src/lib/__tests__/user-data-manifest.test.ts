/**
 * Keeps the account-deletion manifest, the latest `delete_user_data` migration and
 * every Clerk-id column created by supabase/migrations in agreement. A migration
 * that adds a new user-id column without a delete / nullify / keep decision in
 * `user-data-manifest.ts` fails here.
 */
import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';
import {
  DELETE_TABLES,
  KEEP_COLUMNS,
  NULLIFY_COLUMNS,
  isUserIdColumn,
  uncoveredUserIdColumns,
} from '@/lib/user-data-manifest';

const MIGRATIONS_DIR = path.resolve(__dirname, '../../../../supabase/migrations');
/** Latest migration that (re)creates `public.delete_user_data`. */
const DELETE_MIGRATION = '20261013_055_welcome_emails.sql';

/** Lower-cased SQL with `--` comments removed and whitespace collapsed. */
function normalize(sql: string): string {
  return sql
    .replace(/--[^\n]*/g, '')
    .replace(/\s+/g, ' ')
    .toLowerCase();
}

const NAME = String.raw`(?:public\.)?"?(\w+)"?`;
const SKIP_LINE = /^(constraint|primary|unique|foreign|check|exclude|like)\b/;

/** Every (table, column) created by CREATE TABLE or ALTER TABLE ... ADD COLUMN. */
function columnsCreatedBy(sql: string): Array<{ table: string; column: string }> {
  const out: Array<{ table: string; column: string }> = [];
  const text = normalize(sql);

  const create = new RegExp(String.raw`create table (?:if not exists )?${NAME} ?\(`, 'g');
  for (let m = create.exec(text); m; m = create.exec(text)) {
    // Walk to the matching close paren, splitting top-level column definitions.
    let depth = 1;
    let item = '';
    const items: string[] = [];
    for (let i = create.lastIndex; i < text.length && depth > 0; i++) {
      const ch = text[i];
      if (ch === '(') depth++;
      if (ch === ')') depth--;
      if ((ch === ',' && depth === 1) || depth === 0) {
        items.push(item.trim());
        item = '';
      } else {
        item += ch;
      }
    }
    for (const def of items) {
      if (!def || SKIP_LINE.test(def)) continue;
      out.push({ table: m[1], column: def.split(' ')[0].replace(/"/g, '') });
    }
  }

  for (const stmt of text.split(';')) {
    const alter = new RegExp(String.raw`^\s*alter table (?:if exists )?(?:only )?${NAME} `).exec(stmt);
    if (!alter) continue;
    const add = /add column (?:if not exists )?"?(\w+)"?/g;
    for (let m = add.exec(stmt); m; m = add.exec(stmt)) {
      out.push({ table: alter[1], column: m[1] });
    }
  }
  return out;
}

function migrationFiles(): string[] {
  return fs.readdirSync(MIGRATIONS_DIR).filter((f) => f.endsWith('.sql')).sort();
}

const deleteSql = normalize(fs.readFileSync(path.join(MIGRATIONS_DIR, DELETE_MIGRATION), 'utf8'));
const statements = deleteSql.split(';').map((s) => s.trim());

/** Static `delete from public.t where ... col = p_clerk_id ...` statement. */
function staticDeletes(table: string, column: string): boolean {
  return statements.some(
    (s) => s.startsWith(`delete from public.${table} where`) && s.includes(`${column} = p_clerk_id`),
  );
}

/** Guarded `('t', 'col')` entry of the to_regclass delete loop. */
function guardedDeletes(table: string, column: string): boolean {
  return deleteSql.includes(`'${table}', '${column}')`);
}

describe('user-data manifest ↔ latest delete_user_data migration', () => {
  it('every DELETE_TABLES entry is deleted by the SQL', () => {
    for (const { table, columns, via } of DELETE_TABLES) {
      if (via) {
        expect(deleteSql, table).toContain(`delete from public.${table} where`);
        continue;
      }
      for (const column of columns) {
        expect(
          staticDeletes(table, column) || guardedDeletes(table, column),
          `${table}.${column} not deleted in ${DELETE_MIGRATION}`,
        ).toBe(true);
      }
    }
  });

  it('every NULLIFY_COLUMNS entry is set NULL by the SQL', () => {
    for (const { table, column } of NULLIFY_COLUMNS) {
      expect(deleteSql, `${table}.${column}`).toContain(
        `update public.${table} set ${column} = null where ${column} = p_clerk_id`,
      );
    }
  });

  it('the SQL deletes/updates nothing beyond the manifest and never touches KEEP tables', () => {
    const deleted = new Set(DELETE_TABLES.map((d) => d.table));
    const nullified = new Set(NULLIFY_COLUMNS.map((d) => `${d.table}.${d.column}`));
    for (const m of deleteSql.matchAll(/delete from public\.(\w+)/g)) {
      expect(deleted.has(m[1]), `unexpected delete from ${m[1]}`).toBe(true);
    }
    for (const m of deleteSql.matchAll(/'(\w+)', '(\w+)'\)/g)) {
      expect(deleted.has(m[1]), `unexpected guarded delete from ${m[1]}`).toBe(true);
    }
    for (const m of deleteSql.matchAll(/update public\.(\w+) set (\w+) = null/g)) {
      expect(nullified.has(`${m[1]}.${m[2]}`), `unexpected update of ${m[1]}.${m[2]}`).toBe(true);
    }
    for (const { table } of KEEP_COLUMNS) {
      expect(deleteSql).not.toMatch(new RegExp(String.raw`(delete from|update) public\.${table}\b`));
    }
  });

  it('child tables are deleted before their parents', () => {
    const at = (table: string) => deleteSql.search(new RegExp(String.raw`(delete from public\.|')${table}\b`));
    expect(at('coach_messages')).toBeLessThan(at('coach_sessions'));
    expect(at('user_games')).toBeLessThan(at('user_databases'));
    expect(at('analysis_chat_messages')).toBeLessThan(at('analysis_conversations'));
    expect(at('task_attempt')).toBeLessThan(at('task_assignment'));
  });

  it('is locked down to service_role', () => {
    expect(deleteSql).toContain('security definer');
    expect(deleteSql).toContain('set search_path = public');
    expect(deleteSql).toContain(
      'revoke all on function public.delete_user_data(text) from public, anon, authenticated',
    );
    expect(deleteSql).toContain('grant execute on function public.delete_user_data(text) to service_role');
  });

  it('a column is in at most one of DELETE / NULLIFY / KEEP', () => {
    const keys = [
      ...DELETE_TABLES.flatMap((d) => [...d.columns, ...(d.alsoRemoves ?? [])].map((c) => `${d.table}.${c}`)),
      ...NULLIFY_COLUMNS.map((d) => `${d.table}.${d.column}`),
      ...KEEP_COLUMNS.map((d) => `${d.table}.${d.column}`),
    ];
    // organization_members.user_id (delete own rows) and .invited_by (nullify) are distinct columns.
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe('every Clerk-id column in supabase/migrations has a decision', () => {
  it('no uncovered user-id column', () => {
    const columns = migrationFiles().flatMap((f) =>
      columnsCreatedBy(fs.readFileSync(path.join(MIGRATIONS_DIR, f), 'utf8')),
    );
    // Sanity: the scan actually sees the known columns.
    expect(columns).toContainEqual({ table: 'organization_members', column: 'user_id' });
    expect(columns).toContainEqual({ table: 'organization_billing', column: 'whop_user_id' });
    expect(columns).toContainEqual({ table: 'puzzle_rush_school_pick', column: 'user_id' });
    expect(uncoveredUserIdColumns(columns)).toEqual([]);
  });

  it('a new user-id column with no decision fails', () => {
    const columns = columnsCreatedBy(`
      CREATE TABLE IF NOT EXISTS public.new_feature (
        id uuid PRIMARY KEY,
        owner_user_id TEXT NOT NULL, -- Clerk id
        note text,
        CONSTRAINT one_per_owner UNIQUE (owner_user_id)
      );
      ALTER TABLE player_ratings ADD COLUMN IF NOT EXISTS coach_clerk_id TEXT;
    `);
    expect(uncoveredUserIdColumns(columns)).toEqual([
      'new_feature.owner_user_id',
      'player_ratings.coach_clerk_id',
    ]);
  });

  it('matches the user-id column name patterns', () => {
    for (const c of ['user_id', 'clerk_user_id', 'clerk_id', 'owner_user_id', 'created_by', 'whop_user_id', 'white_player_id', 'admin_clerk_id']) {
      expect(isUserIdColumn(c), c).toBe(true);
    }
    for (const c of ['id', 'organization_id', 'external_student_id', 'created_at', 'session_id']) {
      expect(isUserIdColumn(c), c).toBe(false);
    }
  });
});
