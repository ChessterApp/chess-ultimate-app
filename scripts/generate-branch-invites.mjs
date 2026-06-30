#!/usr/bin/env node
/**
 * Branch-invite token generator (one-shot, idempotent).
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc (plan:
 * /root/.claude/plans/ancient-greeting-thimble.md). Run once after the
 * Phase-1 migrations are applied. Generates one branch_invite_tokens row
 * per CE branch with at least one active student, and prints a CSV with
 * the per-branch URL Yerkezhan distributes to parent WhatsApp groups.
 *
 * Idempotent: skips branches that already have a non-revoked token.
 *
 * Required env:
 *   CHESS_EMPIRE_SERVICE_KEY      — CE API key
 *   CHESS_EMPIRE_SUPABASE_URL     — defaults to papgcizhfkngubwofjuo
 *   NEXT_PUBLIC_SUPABASE_URL      — Chesster Supabase project URL
 *   SUPABASE_SERVICE_ROLE_KEY     — Chesster service role
 *
 * Optional:
 *   CHESS_EMPIRE_ORG_SLUG         — defaults to 'chess-empire'
 *   WELCOME_BASE_URL              — defaults to
 *                                  'https://chess-empire.chesster.io/welcome'
 *   DRY_RUN=1                     — emit CSV, don't write tokens
 */

import { randomBytes } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const DEFAULT_CE_BASE = 'https://papgcizhfkngubwofjuo.supabase.co';

function csvEscape(value) {
  const s = String(value ?? '');
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function newToken() {
  return randomBytes(32).toString('base64url');
}

function buildCsv(rows) {
  const header = 'branch_name,active_students,url';
  const body = rows
    .map((r) => `${csvEscape(r.branch_name)},${r.active_students},${csvEscape(r.url)}`)
    .join('\n');
  return `${header}\n${body}\n`;
}

/**
 * Run the generator against injected deps. Pure-ish: no env reads, no fs
 * writes (caller decides). Returns { rows, generated, skippedExisting,
 * skippedEmpty, csv }.
 */
async function run({
  supabase,
  ce,
  orgSlug,
  welcomeBase,
  dryRun = false,
  tokenFactory = newToken,
}) {
  const { data: org, error: orgErr } = await supabase
    .from('organizations')
    .select('id, slug')
    .eq('slug', orgSlug)
    .maybeSingle();
  if (orgErr || !org) {
    throw new Error(`No Chesster org with slug='${orgSlug}': ${orgErr?.message ?? 'not found'}`);
  }

  const branches = await ce.getBranches();
  const rows = [];
  let generated = 0;
  let skippedExisting = 0;
  let skippedEmpty = 0;

  for (const branch of branches) {
    const active = await ce.countActiveStudents(branch.id);
    if (active === 0) {
      skippedEmpty += 1;
      continue;
    }

    const { data: existing } = await supabase
      .from('branch_invite_tokens')
      .select('token')
      .eq('organization_id', org.id)
      .eq('external_branch_id', branch.id)
      .is('revoked_at', null)
      .maybeSingle();

    let token;
    if (existing?.token) {
      token = existing.token;
      skippedExisting += 1;
    } else {
      token = tokenFactory();
      if (!dryRun) {
        const { error: insErr } = await supabase.from('branch_invite_tokens').insert({
          organization_id: org.id,
          external_branch_id: branch.id,
          branch_name: branch.name,
          token,
          created_by: 'generate-branch-invites.mjs',
        });
        if (insErr) {
          throw new Error(`insert failed for ${branch.name}: ${insErr.message}`);
        }
      }
      generated += 1;
    }

    rows.push({
      branch_name: branch.name,
      active_students: active,
      url: `${welcomeBase}/${token}`,
    });
  }

  return {
    rows,
    generated,
    skippedExisting,
    skippedEmpty,
    csv: buildCsv(rows),
  };
}

function requireEnv(name) {
  const v = process.env[name];
  if (!v) {
    console.error(`✗ Missing required env: ${name}`);
    process.exit(1);
  }
  return v;
}

function makeCeClient() {
  const key = requireEnv('CHESS_EMPIRE_SERVICE_KEY');
  const base = (process.env.CHESS_EMPIRE_SUPABASE_URL || DEFAULT_CE_BASE) + '/rest/v1';

  async function ceFetch(pathAndQuery, init = {}) {
    const res = await fetch(`${base}${pathAndQuery}`, {
      ...init,
      headers: {
        apikey: key,
        Authorization: `Bearer ${key}`,
        Accept: 'application/json',
        ...(init.headers || {}),
      },
    });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`CE API ${res.status}: ${body}`);
    }
    return res;
  }

  return {
    async getBranches() {
      const res = await ceFetch('/branches?select=id,name&order=name.asc');
      return res.json();
    },
    async countActiveStudents(branchId) {
      const res = await ceFetch(
        `/students?branch_id=eq.${encodeURIComponent(branchId)}&status=eq.active&select=id`,
        { headers: { Prefer: 'count=exact', Range: '0-0' } },
      );
      const cr = res.headers.get('content-range') || '';
      const m = cr.match(/\/(\d+|\*)$/);
      if (m && m[1] !== '*') return Number(m[1]);
      const body = await res.json();
      return Array.isArray(body) ? body.length : 0;
    },
  };
}

async function main() {
  const orgSlug = process.env.CHESS_EMPIRE_ORG_SLUG || 'chess-empire';
  const welcomeBase = process.env.WELCOME_BASE_URL || 'https://chess-empire.chesster.io/welcome';
  const dryRun = process.env.DRY_RUN === '1';

  // Deferred import so the test harness can load `run`/`buildCsv` without
  // needing @supabase/supabase-js on its module path.
  const { createClient } = await import('@supabase/supabase-js');
  const supabase = createClient(
    requireEnv('NEXT_PUBLIC_SUPABASE_URL'),
    requireEnv('SUPABASE_SERVICE_ROLE_KEY'),
    { auth: { persistSession: false } },
  );

  const ce = makeCeClient();
  console.error(`→ Resolving org slug='${orgSlug}', dry_run=${dryRun}`);

  const result = await run({ supabase, ce, orgSlug, welcomeBase, dryRun });

  process.stdout.write(result.csv);

  const today = new Date().toISOString().slice(0, 10);
  const outDir = path.join(process.cwd(), 'scripts', 'output');
  const outPath = path.join(outDir, `branch-invite-urls-${today}.csv`);
  await mkdir(outDir, { recursive: true });
  await writeFile(outPath, result.csv, 'utf8');

  console.error(
    `\n→ Generated ${result.generated} tokens, skipped ${result.skippedExisting} (already had tokens),`
      + ` skipped ${result.skippedEmpty} branches with 0 active students.`,
  );
  console.error(`→ CSV: ${outPath}`);
  if (dryRun) {
    console.error('→ DRY_RUN=1: no rows written to branch_invite_tokens.');
  }
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main().catch((err) => {
    console.error('✗ Generator failed:', err);
    process.exit(1);
  });
}

export { main, run, buildCsv, csvEscape, newToken };
