#!/usr/bin/env node
/**
 * Chess Empire lifecycle sync (nightly cron).
 *
 * Phase 5 of the Chess Empire → Chesster onboarding arc. Pulls every
 * `organization_members` row where `external_source='chess_empire'`, fetches
 * the current CE profile for each, and reconciles Chesster's `link_status`
 * (+ Clerk org membership) against the authoritative CE `status` column.
 *
 * Reconciliation matrix (CE status × Chesster link_status → action):
 *
 *   | CE status | Chesster link_status | Action                                 |
 *   |-----------|----------------------|----------------------------------------|
 *   | active    | verified             | none                                   |
 *   | active    | frozen               | thaw: link_status='verified',           |
 *   |           |                      | clerk.create_membership (skip 422)     |
 *   | active    | revoked              | none — terminal, needs manual review   |
 *   | active    | pending              | none — parent hasn't finished signup   |
 *   | frozen    | verified             | freeze: link_status='frozen',           |
 *   |           |                      | clerk.delete_membership (skip 404)     |
 *   | frozen    | frozen               | none                                   |
 *   | left      | any except revoked   | revoke: link_status='revoked',          |
 *   |           |                      | clerk.delete_membership (skip 404)     |
 *   | (missing) | any                  | warning, no action                     |
 *
 * Output: writes a run summary to notes/cron/chess-empire-sync-YYYY-MM-DD.md
 * and prints a JSON summary to stdout for log capture.
 *
 * Exit codes:
 *   0 — success
 *   1 — partial failure (some rows errored; details in summary)
 *   2 — total failure (Supabase unreachable etc.)
 *
 * CLI:
 *   node scripts/sync-chess-empire-members.mjs [--dry-run] [--org=<uuid>]
 *
 * Required env:
 *   SUPABASE_URL                 — Chesster Supabase URL
 *   SUPABASE_SERVICE_ROLE_KEY    — Chesster service role
 *   CHESS_EMPIRE_SUPABASE_URL    — defaults to papgcizhfkngubwofjuo
 *   CHESS_EMPIRE_SERVICE_KEY     — CE API key
 *   CLERK_SECRET_KEY             — Clerk backend key
 */

import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const CE_DEFAULT_BASE = 'https://papgcizhfkngubwofjuo.supabase.co';
const CE_BATCH_SIZE = 50;

/**
 * Decide what to do for a single (CE status, Chesster link_status) pair.
 * Returns a plain object with `action` in
 * {'none','thaw','freeze','revoke','missing'} and human-readable `reason`.
 */
export function decideAction(ceStatus, linkStatus) {
  if (ceStatus === null || ceStatus === undefined) {
    return { action: 'missing', reason: 'student not found in CE' };
  }
  if (ceStatus === 'active') {
    if (linkStatus === 'frozen') return { action: 'thaw', reason: 'CE active + link frozen' };
    return { action: 'none', reason: `CE active + link ${linkStatus}` };
  }
  if (ceStatus === 'frozen') {
    if (linkStatus === 'verified') return { action: 'freeze', reason: 'CE frozen + link verified' };
    return { action: 'none', reason: `CE frozen + link ${linkStatus}` };
  }
  if (ceStatus === 'left') {
    if (linkStatus === 'revoked') return { action: 'none', reason: 'CE left + link revoked' };
    return { action: 'revoke', reason: `CE left + link ${linkStatus}` };
  }
  return { action: 'none', reason: `CE ${ceStatus} + link ${linkStatus}` };
}

/**
 * Chunk an array into fixed-size slices — used to keep the `id=in.(…)`
 * query string bounded so PostgREST doesn't reject it.
 */
export function chunk(arr, size) {
  if (size <= 0) throw new Error('chunk size must be > 0');
  const out = [];
  for (let i = 0; i < arr.length; i += size) {
    out.push(arr.slice(i, i + size));
  }
  return out;
}

/**
 * Build the summary markdown from a run result. Pure helper.
 */
export function buildSummaryMd(result, today) {
  const lines = [];
  lines.push(`# Chess Empire lifecycle sync — ${today}`);
  lines.push('');
  lines.push(`**Duration:** ${result.durationSec.toFixed(2)}s`);
  lines.push(`**Members scanned:** ${result.scanned}`);
  lines.push(`**Members fetched from CE:** ${result.fetched}`);
  lines.push(`**Dry run:** ${result.dryRun ? 'yes' : 'no'}`);
  lines.push('**Reconciliations:**');
  lines.push(`- verified→frozen: ${result.counts.freeze}`);
  lines.push(`- frozen→verified: ${result.counts.thaw}`);
  lines.push(`- anything→revoked: ${result.counts.revoke}`);
  lines.push(`- no-op: ${result.counts.none}`);
  lines.push(`**Warnings:** ${result.counts.missing + result.warnings.length}`);
  lines.push(`**Errors:** ${result.errors.length}`);
  lines.push('');
  lines.push('## Details');
  lines.push('');
  const changes = result.details.filter((d) => d.action !== 'none');
  if (changes.length === 0) {
    lines.push('_(no non-no-op changes)_');
  } else {
    lines.push('| member_id | external_student_id | before | after | action | notes |');
    lines.push('|---|---|---|---|---|---|');
    for (const d of changes) {
      lines.push(
        `| ${d.memberId ?? '-'} | ${d.externalStudentId} | ${d.before} | ${d.after ?? d.before} | ${d.action} | ${d.note ?? ''} |`,
      );
    }
  }
  if (result.warnings.length > 0) {
    lines.push('');
    lines.push('## Warnings');
    for (const w of result.warnings) lines.push(`- ${w}`);
  }
  if (result.errors.length > 0) {
    lines.push('');
    lines.push('## Errors');
    for (const e of result.errors) lines.push(`- ${e}`);
  }
  lines.push('');
  lines.push(
    '> Install cron: `0 3 * * * cd /root/chess-app && /usr/bin/node scripts/sync-chess-empire-members.mjs >> /var/log/ce-sync.log 2>&1`',
  );
  lines.push('');
  return lines.join('\n');
}

/**
 * Core reconciliation loop. Injects the supabase / ce / clerk clients so
 * tests can drive it end-to-end without touching the network.
 *
 * Returns { scanned, fetched, counts, warnings, errors, details, dryRun }.
 */
export async function reconcile({
  supabase,
  ce,
  clerk,
  orgFilter = null,
  dryRun = false,
  now = () => new Date(),
}) {
  const started = Date.now();

  const counts = { none: 0, thaw: 0, freeze: 0, revoke: 0, missing: 0 };
  const details = [];
  const warnings = [];
  const errors = [];

  let query = supabase
    .from('organization_members')
    .select('id, organization_id, user_id, external_student_id, link_status, organizations(id, clerk_org_id)')
    .eq('external_source', 'chess_empire');
  if (orgFilter) query = query.eq('organization_id', orgFilter);

  const { data: members, error: memberErr } = await query;
  if (memberErr) {
    throw new Error(`Supabase members select failed: ${memberErr.message}`);
  }
  const rows = members || [];

  // Group by organization for batched CE fetches.
  const perOrg = new Map();
  for (const row of rows) {
    if (!perOrg.has(row.organization_id)) perOrg.set(row.organization_id, []);
    perOrg.get(row.organization_id).push(row);
  }

  let fetched = 0;
  for (const [, orgRows] of perOrg) {
    const ids = orgRows
      .map((r) => r.external_student_id)
      .filter((v) => typeof v === 'string' && v.length > 0);
    const profiles = new Map();
    for (const idBatch of chunk(ids, CE_BATCH_SIZE)) {
      let batchProfiles = [];
      try {
        batchProfiles = await ce.getStudentsByIds(idBatch);
      } catch (exc) {
        errors.push(`CE batch fetch failed (${idBatch.length} ids): ${exc.message}`);
        continue;
      }
      for (const p of batchProfiles) {
        if (p && p.id) profiles.set(p.id, p);
      }
      fetched += batchProfiles.length;
    }

    for (const row of orgRows) {
      const profile = profiles.get(row.external_student_id) || null;
      const decision = decideAction(profile?.status ?? null, row.link_status);

      const detail = {
        memberId: row.id,
        externalStudentId: row.external_student_id,
        before: row.link_status,
        action: decision.action,
        note: decision.reason,
      };

      if (decision.action === 'missing') {
        counts.missing += 1;
        warnings.push(
          `student ${row.external_student_id} missing in CE (member ${row.id})`,
        );
        detail.action = 'none';
        counts.none += 1;
        details.push(detail);
        continue;
      }

      if (decision.action === 'none') {
        counts.none += 1;
        details.push(detail);
        continue;
      }

      const clerkOrgId = row.organizations?.clerk_org_id;
      const nowIso = now().toISOString();

      try {
        if (decision.action === 'thaw') {
          detail.after = 'verified';
          if (!dryRun) {
            await supabase
              .from('organization_members')
              .update({ link_status: 'verified', link_verified_at: nowIso })
              .eq('id', row.id);
            if (clerkOrgId) {
              await clerk.createMembership(clerkOrgId, row.user_id, 'basic_member');
            }
          }
          counts.thaw += 1;
        } else if (decision.action === 'freeze') {
          detail.after = 'frozen';
          if (!dryRun) {
            await supabase
              .from('organization_members')
              .update({ link_status: 'frozen' })
              .eq('id', row.id);
            if (clerkOrgId) {
              await clerk.deleteMembership(clerkOrgId, row.user_id);
            }
          }
          counts.freeze += 1;
        } else if (decision.action === 'revoke') {
          detail.after = 'revoked';
          if (!dryRun) {
            await supabase
              .from('organization_members')
              .update({ link_status: 'revoked', link_revoked_at: nowIso })
              .eq('id', row.id);
            if (clerkOrgId) {
              await clerk.deleteMembership(clerkOrgId, row.user_id);
            }
          }
          counts.revoke += 1;
        }
      } catch (exc) {
        errors.push(`reconcile ${decision.action} member ${row.id}: ${exc.message}`);
      }

      details.push(detail);
    }
  }

  return {
    scanned: rows.length,
    fetched,
    counts,
    warnings,
    errors,
    details,
    dryRun,
    durationSec: (Date.now() - started) / 1000,
  };
}

function parseArgs(argv) {
  const args = { dryRun: false, org: null };
  for (const a of argv) {
    if (a === '--dry-run') args.dryRun = true;
    else if (a.startsWith('--org=')) args.org = a.slice('--org='.length);
  }
  return args;
}

function requireEnv(name) {
  const v = process.env[name];
  if (!v) {
    console.error(`✗ Missing required env: ${name}`);
    process.exit(2);
  }
  return v;
}

/**
 * Build a real Chess Empire client that returns rows matching the
 * `analytics-students` profile shape — we only need `id` and `status`.
 * Uses PostgREST `id=in.(…)` on the students table.
 */
function makeCeClient() {
  const key = requireEnv('CHESS_EMPIRE_SERVICE_KEY');
  const base = (process.env.CHESS_EMPIRE_SUPABASE_URL || CE_DEFAULT_BASE) + '/rest/v1';

  return {
    async getStudentsByIds(ids) {
      if (ids.length === 0) return [];
      const q = ids.map((id) => encodeURIComponent(id)).join(',');
      const url = `${base}/students?select=id,status&id=in.(${q})`;
      const res = await fetch(url, {
        headers: {
          apikey: key,
          Authorization: `Bearer ${key}`,
          Accept: 'application/json',
        },
      });
      if (!res.ok) {
        const body = await res.text().catch(() => '');
        throw new Error(`CE API ${res.status}: ${body}`);
      }
      return res.json();
    },
  };
}

function makeClerkClient() {
  const key = requireEnv('CLERK_SECRET_KEY');
  const base = 'https://api.clerk.com/v1';

  async function call(method, pathAndQuery, body) {
    const res = await fetch(`${base}${pathAndQuery}`, {
      method,
      headers: {
        Authorization: `Bearer ${key}`,
        'Content-Type': 'application/json',
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    return res;
  }

  return {
    async createMembership(orgId, userId, role) {
      const res = await call('POST', `/organizations/${orgId}/memberships`, {
        user_id: userId, role,
      });
      if (res.status === 422) return; // already a member
      if (!res.ok) {
        const t = await res.text().catch(() => '');
        throw new Error(`Clerk create_membership ${res.status}: ${t}`);
      }
    },
    async deleteMembership(orgId, userId) {
      const res = await call('DELETE', `/organizations/${orgId}/memberships/${userId}`);
      if (res.status === 404) return; // already gone
      if (!res.ok) {
        const t = await res.text().catch(() => '');
        throw new Error(`Clerk delete_membership ${res.status}: ${t}`);
      }
    },
  };
}

export async function writeSummary(result, today, outDir = null) {
  const target = outDir || path.join(process.cwd(), 'notes', 'cron');
  await mkdir(target, { recursive: true });
  const outPath = path.join(target, `chess-empire-sync-${today}.md`);
  await writeFile(outPath, buildSummaryMd(result, today), 'utf8');
  return outPath;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));

  let supabase;
  try {
    const { createClient } = await import('@supabase/supabase-js');
    supabase = createClient(
      requireEnv('SUPABASE_URL'),
      requireEnv('SUPABASE_SERVICE_ROLE_KEY'),
      { auth: { persistSession: false } },
    );
  } catch (exc) {
    console.error('✗ Failed to init Supabase client:', exc.message);
    process.exit(2);
  }

  const ce = makeCeClient();
  const clerk = makeClerkClient();

  let result;
  try {
    result = await reconcile({
      supabase,
      ce,
      clerk,
      orgFilter: args.org,
      dryRun: args.dryRun,
    });
  } catch (exc) {
    console.error('✗ Reconcile failed catastrophically:', exc.message);
    process.exit(2);
  }

  const today = new Date().toISOString().slice(0, 10);
  const outPath = await writeSummary(result, today);

  const summary = {
    ok: result.errors.length === 0,
    scanned: result.scanned,
    fetched: result.fetched,
    counts: result.counts,
    warnings: result.warnings.length,
    errors: result.errors.length,
    dryRun: result.dryRun,
    org: args.org,
    outPath,
  };
  process.stdout.write(`${JSON.stringify(summary)}\n`);

  if (result.errors.length > 0) process.exit(1);
  process.exit(0);
}

const isMain = import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main().catch((err) => {
    console.error('✗ Cron failed:', err);
    process.exit(2);
  });
}
