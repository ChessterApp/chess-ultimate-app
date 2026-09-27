import type { AccessPolicy } from '@/lib/access-policy'

export interface GatingCourse {
  id: string
  order_index: number
}

/**
 * Compute lock state per course for the learn path.
 *
 * Regular Chesster users (ceLevelFloor undefined): progressive unlock.
 *   - The first course (lowest order_index) is always unlocked.
 *   - Every later course is unlocked ONLY if the immediately-previous
 *     course (by order_index) has progress === 100.
 *
 * `ceLevelFloor` (Chess Empire students): when provided, a course is unlocked
 * if its 1-based position in the order_index-sorted list is <= ceLevelFloor,
 * OR the previous course is complete. Position (not raw order_index) is used
 * because the DB order_index values are not 1-based (they run 3..10), whereas
 * the CE current_level is 1..8. Level N ↔ the Nth course on the path.
 *
 * `restrictedCeiling` (frozen/expired members): when provided, every course at
 * a 1-based position GREATER than the ceiling is ALWAYS locked — even when the
 * previous course is complete and even when `ceLevelFloor` would otherwise
 * unlock it. This is the Learn-side restriction: a paused/expired member may
 * only reach their current level plus everything below it. It overrides both
 * `prevComplete` and `ceLevelFloor`, but never the ownComplete invariant.
 *
 * A course whose OWN progress is 100 is always unlocked — you can never lock a
 * course the user has already fully completed, regardless of earlier courses'
 * state (a user may finish a later course before an earlier one is at 100%).
 * This invariant wins over `restrictedCeiling` too.
 *
 * @param courses           courses to gate (any order; sorted internally by order_index asc)
 * @param progressMap       map of courseId -> { progress } (0..100)
 * @param ceLevelFloor      optional CE current_level (1..8); undefined for regular users
 * @param restrictedCeiling optional 1-based position of a restricted member's
 *                          current level; courses above it are hard-locked.
 * @returns map of courseId -> isLocked (boolean)
 */
export function computeLockStates(
  courses: GatingCourse[],
  progressMap: Record<string, { progress: number }>,
  ceLevelFloor?: number,
  restrictedCeiling?: number
): Record<string, boolean> {
  const sorted = [...courses].sort((a, b) => a.order_index - b.order_index)

  const lockStates: Record<string, boolean> = {}

  sorted.forEach((course, i) => {
    const prevComplete =
      i === 0
        ? true
        : (progressMap[sorted[i - 1].id]?.progress ?? 0) === 100

    const ownComplete = (progressMap[course.id]?.progress ?? 0) === 100

    let unlocked =
      i === 0 ||
      prevComplete ||
      ownComplete ||
      (ceLevelFloor !== undefined && i + 1 <= ceLevelFloor)

    // A restricted member is hard-capped at their current level: anything above
    // the ceiling is locked regardless of progression/floor unlocks, unless the
    // course itself is already fully complete (the ownComplete invariant).
    if (
      restrictedCeiling !== undefined &&
      i + 1 > restrictedCeiling &&
      !ownComplete
    ) {
      unlocked = false
    }

    lockStates[course.id] = !unlocked
  })

  return lockStates
}

/**
 * Resolve a restricted member's Learn ceiling — the 1-based position of the
 * level they are currently on. Pure and framework-free (like `computeLockStates`)
 * so it runs identically on the server guard and in the client `LearnClient`.
 *
 * - `undefined` when the member has full access (no ceiling applies).
 * - Otherwise the position of the FIRST course (order_index asc) whose progress
 *   is below 100 — the level they still have to finish.
 * - If every course is complete, the last position (nothing new unlocks; the
 *   level-complete conversion screen has already handled the messaging).
 * - `undefined` for an empty course list (nothing to gate).
 *
 * @param policy      the member's resolved access policy
 * @param courses     courses to gate (any order; sorted internally by order_index asc)
 * @param progressMap map of courseId -> { progress } (0..100)
 */
export function resolveRestrictedCeiling(
  policy: Pick<AccessPolicy, 'mode'>,
  courses: GatingCourse[],
  progressMap: Record<string, { progress: number }>
): number | undefined {
  if (policy.mode === 'full') return undefined
  if (courses.length === 0) return undefined

  const sorted = [...courses].sort((a, b) => a.order_index - b.order_index)
  const firstIncomplete = sorted.findIndex(
    (c) => (progressMap[c.id]?.progress ?? 0) < 100
  )
  if (firstIncomplete === -1) return sorted.length
  return firstIncomplete + 1
}

/** URL-friendly slug from a title — mirrors the backend `generate_slug_from_title`. */
export function slugifyTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}
