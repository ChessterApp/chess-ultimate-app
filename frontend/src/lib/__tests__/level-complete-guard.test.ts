import { describe, it, expect } from 'vitest'
import { shouldShowLevelComplete } from '../level-complete-guard'

function memoryStorage(): Pick<Storage, 'getItem' | 'setItem'> {
  const map = new Map<string, string>()
  return {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, v),
  }
}

describe('shouldShowLevelComplete', () => {
  it('returns true the first time a course completion is seen', () => {
    const store = memoryStorage()
    expect(shouldShowLevelComplete('course-a', store)).toBe(true)
  })

  it('returns false on every later call for the same course', () => {
    const store = memoryStorage()
    expect(shouldShowLevelComplete('course-a', store)).toBe(true)
    expect(shouldShowLevelComplete('course-a', store)).toBe(false)
    expect(shouldShowLevelComplete('course-a', store)).toBe(false)
  })

  it('tracks each course independently', () => {
    const store = memoryStorage()
    expect(shouldShowLevelComplete('course-a', store)).toBe(true)
    expect(shouldShowLevelComplete('course-b', store)).toBe(true)
    expect(shouldShowLevelComplete('course-a', store)).toBe(false)
  })
})
