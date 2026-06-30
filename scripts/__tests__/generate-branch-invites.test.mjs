/**
 * Tests for scripts/generate-branch-invites.mjs.
 *
 * Drives the exported `run(deps)` with mocked CE + Chesster, then verifies:
 *   - branches with 0 active students are skipped
 *   - branches with an existing non-revoked token reuse it (no insert)
 *   - new branches get a token inserted with the canonical created_by tag
 *   - CSV header + escaping format
 *
 * Uses node:test (no extra deps). Run with:
 *   node --test scripts/__tests__/generate-branch-invites.test.mjs
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  run,
  buildCsv,
  csvEscape,
  newToken,
} from '../generate-branch-invites.mjs';

function makeSupabase(scripts, recorder) {
  return {
    from(table) {
      const rec = { table, op: 'select', filters: [], payload: null };
      const finalize = (op) => {
        rec.op = op;
        recorder.push(rec);
        const queue = scripts[`${table}.${op}`] || [];
        return Promise.resolve(queue.shift() ?? { data: null, error: null });
      };
      const chain = {
        select() { return chain; },
        eq(c, v) { rec.filters.push([c, v]); return chain; },
        is(c, v) { rec.filters.push([c, v]); return chain; },
        maybeSingle() { return finalize('maybeSingle'); },
        insert(payload) {
          rec.op = 'insert';
          rec.payload = payload;
          recorder.push(rec);
          const queue = scripts[`${table}.insert`] || [];
          return Promise.resolve(queue.shift() ?? { data: null, error: null });
        },
      };
      return chain;
    },
  };
}

test('skips branches with 0 active students', async () => {
  const scripts = {
    'organizations.maybeSingle': [{ data: { id: 'org-1', slug: 'chess-empire' }, error: null }],
    'branch_invite_tokens.maybeSingle': [{ data: null, error: null }],
    'branch_invite_tokens.insert': [{ data: null, error: null }],
  };
  const recorder = [];
  const ce = {
    getBranches: async () => [
      { id: 'br-1', name: 'Debut' },
      { id: 'br-2', name: 'NIS' },
    ],
    countActiveStudents: async (id) => (id === 'br-1' ? 100 : 0),
  };
  const result = await run({
    supabase: makeSupabase(scripts, recorder),
    ce,
    orgSlug: 'chess-empire',
    welcomeBase: 'https://example.test/welcome',
    tokenFactory: () => 'TOKEN_FIXED',
  });
  assert.equal(result.generated, 1);
  assert.equal(result.skippedEmpty, 1);
  assert.equal(result.skippedExisting, 0);
  assert.equal(result.rows.length, 1);
  assert.equal(result.rows[0].branch_name, 'Debut');
  assert.equal(result.rows[0].active_students, 100);
  assert.equal(result.rows[0].url, 'https://example.test/welcome/TOKEN_FIXED');
});

test('reuses existing non-revoked tokens (idempotent)', async () => {
  const scripts = {
    'organizations.maybeSingle': [{ data: { id: 'org-1' }, error: null }],
    'branch_invite_tokens.maybeSingle': [
      { data: { token: 'EXISTING_TOKEN' }, error: null },
    ],
  };
  const recorder = [];
  const ce = {
    getBranches: async () => [{ id: 'br-1', name: 'Debut' }],
    countActiveStudents: async () => 50,
  };
  const result = await run({
    supabase: makeSupabase(scripts, recorder),
    ce,
    orgSlug: 'chess-empire',
    welcomeBase: 'https://example.test/welcome',
    tokenFactory: () => 'SHOULD_NOT_BE_USED',
  });
  assert.equal(result.generated, 0);
  assert.equal(result.skippedExisting, 1);
  assert.equal(result.rows[0].url, 'https://example.test/welcome/EXISTING_TOKEN');
  // No insert recorded.
  assert.equal(
    recorder.find((r) => r.op === 'insert'),
    undefined,
  );
});

test('inserts new token with canonical created_by tag', async () => {
  const scripts = {
    'organizations.maybeSingle': [{ data: { id: 'org-1' }, error: null }],
    'branch_invite_tokens.maybeSingle': [{ data: null, error: null }],
    'branch_invite_tokens.insert': [{ data: null, error: null }],
  };
  const recorder = [];
  const ce = {
    getBranches: async () => [{ id: 'br-1', name: 'Debut' }],
    countActiveStudents: async () => 10,
  };
  await run({
    supabase: makeSupabase(scripts, recorder),
    ce,
    orgSlug: 'chess-empire',
    welcomeBase: 'https://example.test/welcome',
    tokenFactory: () => 'NEW',
  });
  const insert = recorder.find((r) => r.op === 'insert');
  assert.ok(insert, 'expected an insert');
  assert.equal(insert.payload.created_by, 'generate-branch-invites.mjs');
  assert.equal(insert.payload.organization_id, 'org-1');
  assert.equal(insert.payload.external_branch_id, 'br-1');
  assert.equal(insert.payload.token, 'NEW');
});

test('does not insert under dryRun', async () => {
  const scripts = {
    'organizations.maybeSingle': [{ data: { id: 'org-1' }, error: null }],
    'branch_invite_tokens.maybeSingle': [{ data: null, error: null }],
  };
  const recorder = [];
  const ce = {
    getBranches: async () => [{ id: 'br-1', name: 'Debut' }],
    countActiveStudents: async () => 10,
  };
  const result = await run({
    supabase: makeSupabase(scripts, recorder),
    ce,
    orgSlug: 'chess-empire',
    welcomeBase: 'https://example.test/welcome',
    dryRun: true,
    tokenFactory: () => 'DRY',
  });
  assert.equal(result.generated, 1);
  assert.equal(recorder.find((r) => r.op === 'insert'), undefined);
});

test('buildCsv emits header + rows', () => {
  const csv = buildCsv([
    { branch_name: 'Debut', active_students: 262, url: 'https://x/y' },
  ]);
  assert.ok(csv.startsWith('branch_name,active_students,url\n'));
  assert.ok(csv.includes('Debut,262,https://x/y'));
});

test('csvEscape quotes strings with commas / quotes / newlines', () => {
  assert.equal(csvEscape('plain'), 'plain');
  assert.equal(csvEscape('a,b'), '"a,b"');
  assert.equal(csvEscape('he said "hi"'), '"he said ""hi"""');
  assert.equal(csvEscape('one\ntwo'), '"one\ntwo"');
});

test('newToken returns a 32-byte base64url string', () => {
  const t = newToken();
  assert.equal(typeof t, 'string');
  assert.ok(t.length >= 40);
  assert.ok(/^[A-Za-z0-9_-]+$/.test(t));
});
