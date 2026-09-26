import { describe, it, expect } from 'vitest'
import {
  computeLockStates,
  resolveRestrictedCeiling,
  slugifyTitle,
  type GatingCourse,
} from '../learn-gating'

// Helper: build N courses with order_index 1..N and ids "c1".."cN".
function makeCourses(n: number): GatingCourse[] {
  return Array.from({ length: n }, (_, i) => ({ id: `c${i + 1}`, order_index: i + 1 }))
}

// Helper: progress map from a partial { id: progress } record.
function makeProgress(entries: Record<string, number>): Record<string, { progress: number }> {
  const map: Record<string, { progress: number }> = {}
  for (const [id, progress] of Object.entries(entries)) {
    map[id] = { progress }
  }
  return map
}

describe('computeLockStates', () => {
  it('returns {} for empty courses', () => {
    expect(computeLockStates([], {})).toEqual({})
  })

  it('single course is always unlocked', () => {
    const result = computeLockStates(makeCourses(1), {})
    expect(result).toEqual({ c1: false })
  })

  it('8 courses none complete: only first unlocked', () => {
    const result = computeLockStates(makeCourses(8), {})
    expect(result.c1).toBe(false)
    for (let i = 2; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true)
    }
  })

  it('course 1 at 100: courses 1 & 2 unlocked, 3-8 locked (cascade)', () => {
    const result = computeLockStates(makeCourses(8), makeProgress({ c1: 100 }))
    expect(result.c1).toBe(false)
    expect(result.c2).toBe(false)
    for (let i = 3; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true)
    }
  })

  it('courses 1-3 at 100: courses 1-4 unlocked, 5-8 locked', () => {
    const result = computeLockStates(
      makeCourses(8),
      makeProgress({ c1: 100, c2: 100, c3: 100 })
    )
    for (let i = 1; i <= 4; i++) {
      expect(result[`c${i}`]).toBe(false)
    }
    for (let i = 5; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true)
    }
  })

  it('scrambled input order_index is still gated correctly and input is not mutated', () => {
    const courses: GatingCourse[] = [
      { id: 'c3', order_index: 3 },
      { id: 'c1', order_index: 1 },
      { id: 'c2', order_index: 2 },
    ]
    const snapshot = courses.map((c) => ({ ...c }))
    const result = computeLockStates(courses, makeProgress({ c1: 100 }))
    expect(result).toEqual({ c1: false, c2: false, c3: true })
    // input array not mutated (same order, same contents)
    expect(courses).toEqual(snapshot)
  })

  it('missing progress entry is treated as 0 (locked unless first)', () => {
    const result = computeLockStates(makeCourses(3), {})
    expect(result).toEqual({ c1: false, c2: true, c3: true })
  })

  it('ceLevelFloor=3 with no progress: order_index 1,2,3 unlocked, 4-8 locked', () => {
    const result = computeLockStates(makeCourses(8), {}, 3)
    for (let i = 1; i <= 3; i++) {
      expect(result[`c${i}`]).toBe(false)
    }
    for (let i = 4; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true)
    }
  })

  it('ceLevelFloor gates by 1-based position, not raw order_index (prod order_index runs 3..10)', () => {
    // Production courses are ordered but NOT 1-based: order_index 3,4,5,...,10.
    // A CE student at level 3 must get the first 3 courses (positions 1-3),
    // regardless of the raw order_index values.
    const courses: GatingCourse[] = Array.from({ length: 8 }, (_, i) => ({
      id: `c${i + 1}`,
      order_index: i + 3, // 3,4,5,6,7,8,9,10
    }))
    const result = computeLockStates(courses, {}, 3)
    // positions 1,2,3 unlocked
    expect(result.c1).toBe(false)
    expect(result.c2).toBe(false)
    expect(result.c3).toBe(false)
    // positions 4-8 locked
    for (let i = 4; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true)
    }
  })

  it('a course whose own progress is 100 is never locked, even if an earlier course is incomplete', () => {
    // Omar's real case: course 5 is 100% complete but course 4 sits at 93%.
    // Without the ownComplete clause, course 5 renders locked (prevComplete=false)
    // while course 6 (97%, unfinished) renders open — a completed level padlocked.
    const result = computeLockStates(
      makeCourses(8),
      makeProgress({ c1: 100, c2: 100, c3: 100, c4: 93, c5: 100, c6: 97 })
    )
    expect(result.c5).toBe(false) // fully completed -> never locked
    // c4 (93) gates via prevComplete: c1-3 done -> c4 unlocked; c4 not 100 -> c5 would
    // be locked without ownComplete; c6 unlocked because c5 is 100.
    expect(result.c6).toBe(false)
    expect(result.c7).toBe(true) // c6 not 100 -> c7 stays locked
    expect(result.c8).toBe(true)
  })

  it('completed course is unlocked regardless of ceLevelFloor and earlier gaps', () => {
    // CE student at floor 2 who completed course 6 in-app: 1-2 via floor, 6 via ownComplete.
    const result = computeLockStates(makeCourses(8), makeProgress({ c6: 100 }), 2)
    expect(result.c1).toBe(false)
    expect(result.c2).toBe(false)
    expect(result.c3).toBe(true) // above floor, prev not complete
    expect(result.c6).toBe(false) // own progress 100 -> unlocked
    expect(result.c7).toBe(false) // prev (c6) complete
  })

  it('CE student at level 3 who also completed course 4 unlocks course 5 via prevComplete', () => {
    // Floor unlocks 1-3; completing course 4 in-app (progress 100) makes course
    // 5 unlocked via prevComplete even though the floor alone would not reach it.
    const result = computeLockStates(makeCourses(8), makeProgress({ c4: 100 }), 3)
    expect(result.c1).toBe(false)
    expect(result.c2).toBe(false)
    expect(result.c3).toBe(false)
    expect(result.c5).toBe(false) // unlocked because previous course (4) is complete
    for (const i of [6, 7, 8]) {
      expect(result[`c${i}`]).toBe(true)
    }
  })

  // ---- restrictedCeiling ---------------------------------------------------

  it('restrictedCeiling locks courses above the ceiling even when the previous course is complete', () => {
    // Courses 1-3 complete would normally unlock course 4 via prevComplete, but
    // a restricted member capped at level 3 must not reach it.
    const result = computeLockStates(
      makeCourses(8),
      makeProgress({ c1: 100, c2: 100, c3: 100 }),
      undefined,
      3
    )
    expect(result.c1).toBe(false)
    expect(result.c2).toBe(false)
    expect(result.c3).toBe(false)
    for (let i = 4; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true) // hard-capped above the ceiling
    }
  })

  it('restrictedCeiling never re-locks a course whose own progress is 100', () => {
    // Course 6 (above the ceiling of 3) is already fully complete — the
    // ownComplete invariant beats the ceiling.
    const result = computeLockStates(
      makeCourses(8),
      makeProgress({ c1: 100, c2: 100, c3: 100, c6: 100 }),
      undefined,
      3
    )
    expect(result.c4).toBe(true) // above ceiling, not complete -> locked
    expect(result.c5).toBe(true)
    expect(result.c6).toBe(false) // own progress 100 -> stays unlocked
    // c7's previous (c6) is complete, but c7 is above the ceiling and not itself
    // complete, so the ceiling clamps it shut regardless of prevComplete.
    expect(result.c7).toBe(true)
  })

  it('undefined restrictedCeiling is identical to legacy behavior', () => {
    const progress = makeProgress({ c1: 100, c2: 100 })
    const legacy = computeLockStates(makeCourses(8), progress, 3)
    const withUndefined = computeLockStates(makeCourses(8), progress, 3, undefined)
    expect(withUndefined).toEqual(legacy)
  })

  it('restricted CE student: the ceiling wins over a higher ceLevelFloor', () => {
    // A frozen CE student has floor 5 (level 5) but a ceiling of 2 (only
    // completed 1, working on 2). The ceiling must clamp the floor's unlocks.
    const result = computeLockStates(
      makeCourses(8),
      makeProgress({ c1: 100 }),
      5, // ceLevelFloor
      2 // restrictedCeiling
    )
    expect(result.c1).toBe(false) // completed
    expect(result.c2).toBe(false) // at the ceiling
    for (let i = 3; i <= 8; i++) {
      expect(result[`c${i}`]).toBe(true) // floor would open 3-5, ceiling clamps
    }
  })
})

describe('resolveRestrictedCeiling', () => {
  it('returns undefined for a full-access policy', () => {
    expect(
      resolveRestrictedCeiling({ mode: 'full' }, makeCourses(5), {})
    ).toBeUndefined()
  })

  it('returns undefined for an empty course list', () => {
    expect(resolveRestrictedCeiling({ mode: 'restricted' }, [], {})).toBeUndefined()
  })

  it('restricted, no progress: current level is the first course', () => {
    expect(
      resolveRestrictedCeiling({ mode: 'restricted' }, makeCourses(5), {})
    ).toBe(1)
  })

  it('restricted: current level is the first course whose progress < 100', () => {
    const result = resolveRestrictedCeiling(
      { mode: 'restricted' },
      makeCourses(5),
      makeProgress({ c1: 100, c2: 100, c3: 40 })
    )
    expect(result).toBe(3)
  })

  it('restricted, everything complete: returns the last position', () => {
    const result = resolveRestrictedCeiling(
      { mode: 'restricted' },
      makeCourses(5),
      makeProgress({ c1: 100, c2: 100, c3: 100, c4: 100, c5: 100 })
    )
    expect(result).toBe(5)
  })

  it('resolves by 1-based position from scrambled input (order_index not 1-based)', () => {
    const courses: GatingCourse[] = [
      { id: 'c3', order_index: 10 },
      { id: 'c1', order_index: 3 },
      { id: 'c2', order_index: 4 },
    ]
    // c1 complete, c2 incomplete -> current level is position 2.
    const result = resolveRestrictedCeiling(
      { mode: 'restricted' },
      courses,
      makeProgress({ c1: 100 })
    )
    expect(result).toBe(2)
  })
})

describe('slugifyTitle', () => {
  it('matches the backend generate_slug_from_title behavior', () => {
    expect(slugifyTitle('Chess Fundamentals')).toBe('chess-fundamentals')
    expect(slugifyTitle('  King & Pawn  ')).toBe('king-pawn')
    expect(slugifyTitle('Level 1: Basics!')).toBe('level-1-basics')
  })
})
