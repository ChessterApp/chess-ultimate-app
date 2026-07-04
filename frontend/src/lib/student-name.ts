/**
 * Single allowed resolver for the user-facing student display name.
 *
 * Phase 3 of the "robust email ↔ CE student linking" arc (plan:
 * /root/.claude/plans/melodic-noodling-micali.md). The plan explicitly forbids
 * ever falling back to a Clerk field, email prefix, or any other identity
 * source when rendering a greeting on tenant surfaces. Callers must switch to
 * name-less copy when this returns null.
 *
 * Resolution order:
 *   1. `students.first_name` (CE column), trimmed — used as-is if non-empty.
 *   2. First token of `students.full_name` if `first_name` is null/blank —
 *      Cyrillic-safe split on any whitespace.
 *   3. null — caller must render name-less copy ("Welcome back", not
 *      "Welcome back, dagamavasco210").
 */
import 'server-only';

export interface StudentNameInput {
  first_name?: string | null;
  full_name?: string | null;
}

const WHITESPACE_RE = /\s+/u;

export function resolveStudentDisplayName(
  student: StudentNameInput | null | undefined,
): string | null {
  if (!student) return null;

  const rawFirst =
    typeof student.first_name === 'string' ? student.first_name : '';
  const first = rawFirst.trim();
  if (first.length > 0) return first;

  const rawFull =
    typeof student.full_name === 'string' ? student.full_name : '';
  const full = rawFull.trim();
  if (full.length > 0) {
    const token = full.split(WHITESPACE_RE)[0]?.trim() ?? '';
    if (token.length > 0) return token;
  }

  return null;
}
