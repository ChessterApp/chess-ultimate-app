/**
 * Schema-drift guard for organization_members.role.
 *
 * On 2026-07-10 coach self-registration silently failed for hours because
 * chess-empire-jwt-link.ts wrote role='coach' while the DB check constraint
 * (20260428_001) only allowed owner/admin/teacher/student. This test parses
 * the migrations for the *effective* (latest) role check constraint and
 * asserts every role value the app writes is permitted by it, so code and
 * schema can't drift apart without a failing test.
 */
import { describe, it, expect } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * Every role value the app writes to organization_members. Sources:
 * - chess-empire-jwt-link.ts: role = memberType === 'coach' ? 'coach' : 'student'
 * - org creation flow: 'owner'
 * If you add a new role literal in code, add it here — the test then forces
 * a migration widening the check constraint before it can pass.
 */
const APP_WRITTEN_ROLES = ['owner', 'student', 'coach'];

const MIGRATIONS_DIR = join(
  dirname(fileURLToPath(import.meta.url)),
  '../../../../supabase/migrations',
);

/** Extract allowed values from the latest role CHECK on organization_members. */
function effectiveAllowedRoles(): { file: string; roles: string[] } {
  const files = readdirSync(MIGRATIONS_DIR)
    .filter((f) => f.endsWith('.sql'))
    .sort();

  let latest: { file: string; roles: string[] } | null = null;

  for (const file of files) {
    const sql = readFileSync(join(MIGRATIONS_DIR, file), 'utf8')
      // Strip line comments so rollback instructions don't parse as checks.
      .replace(/--[^\n]*/g, '');
    // Match both the inline column check in CREATE TABLE organization_members
    // and later ADD CONSTRAINT organization_members_role_check forms. The
    // (?<![\w.]) guard skips policy predicates like "om.role IN (...)".
    const isOrgMembers =
      /CREATE TABLE (IF NOT EXISTS )?organization_members\b/i.test(sql) ||
      /organization_members_role_check/.test(sql);
    if (!isOrgMembers) continue;

    const checks = [...sql.matchAll(/(?<![\w.])role\s+IN\s*\(([^)]*)\)/gi)];
    if (checks.length === 0) continue;

    const last = checks[checks.length - 1][1];
    const roles = [...last.matchAll(/'([^']*)'/g)].map((m) => m[1]);
    latest = { file, roles };
  }

  if (!latest) throw new Error('No role check constraint found in migrations');
  return latest;
}

describe('organization_members role check constraint', () => {
  it('permits every role value the app writes', () => {
    const { file, roles } = effectiveAllowedRoles();
    for (const role of APP_WRITTEN_ROLES) {
      expect(roles, `role '${role}' missing from check in ${file}`).toContain(role);
    }
  });

  it("includes 'coach' (regression: 2026-07-10 coach link failure)", () => {
    expect(effectiveAllowedRoles().roles).toContain('coach');
  });
});
