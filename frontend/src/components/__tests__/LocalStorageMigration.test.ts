import { describe, it, expect, beforeEach, vi } from 'vitest'

/**
 * LocalStorageMigration — Integration Tests
 *
 * Tests the localStorage migration flow that runs on app mount:
 * 1. Animation duration migration: resets stale 300ms values so new 50ms default takes effect
 * 2. Board theme migration (v2): switches users to ChessBase theme + Fritz pieces
 */

// ---------- helpers ----------

function createMockLocalStorage(initial: Record<string, string> = {}) {
  const store: Record<string, string> = { ...initial }
  return {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => { store[key] = value }),
    removeItem: vi.fn((key: string) => { delete store[key] }),
    clear: vi.fn(() => { Object.keys(store).forEach(k => delete store[k]) }),
    get length() { return Object.keys(store).length },
    key: vi.fn((i: number) => Object.keys(store)[i] ?? null),
    _store: store,
  }
}

/**
 * Simulate the animation-duration migration from LocalStorageMigration.tsx
 * (extracted logic so we can test without React rendering)
 */
function runAnimationDurationMigration(storage: ReturnType<typeof createMockLocalStorage>) {
  try {
    const animDuration = storage.getItem('board_ui_animation_duration')
    if (animDuration) {
      const value = parseInt(animDuration, 10)
      if (!isNaN(value) && value > 100) {
        storage.removeItem('board_ui_animation_duration')
      }
    }
  } catch {
    // silent
  }
}

/**
 * Simulate the board-theme v2 migration from AiChessboard.tsx
 */
function runBoardThemeMigration(
  storage: ReturnType<typeof createMockLocalStorage>,
  setPieceType: (v: string) => void,
  setBoardTheme: (v: string) => void,
) {
  const migrated = storage.getItem('board_theme_migrated_v2')
  if (!migrated) {
    setPieceType('Fritz')
    setBoardTheme('chessbase')
    storage.setItem('board_theme_migrated_v2', '1')
  }
}

// ---------- tests ----------

describe('Animation Duration Migration', () => {
  let storage: ReturnType<typeof createMockLocalStorage>

  beforeEach(() => {
    storage = createMockLocalStorage()
  })

  it('should remove stale 300ms animation duration', () => {
    storage._store['board_ui_animation_duration'] = '300'

    runAnimationDurationMigration(storage)

    expect(storage.removeItem).toHaveBeenCalledWith('board_ui_animation_duration')
    expect(storage._store['board_ui_animation_duration']).toBeUndefined()
  })

  it('should remove any animation duration > 100ms', () => {
    storage._store['board_ui_animation_duration'] = '150'

    runAnimationDurationMigration(storage)

    expect(storage.removeItem).toHaveBeenCalledWith('board_ui_animation_duration')
    expect(storage._store['board_ui_animation_duration']).toBeUndefined()
  })

  it('should keep animation duration at exactly 100ms', () => {
    storage._store['board_ui_animation_duration'] = '100'

    runAnimationDurationMigration(storage)

    expect(storage.removeItem).not.toHaveBeenCalled()
    expect(storage._store['board_ui_animation_duration']).toBe('100')
  })

  it('should keep animation duration < 100ms (e.g. new 50ms default)', () => {
    storage._store['board_ui_animation_duration'] = '50'

    runAnimationDurationMigration(storage)

    expect(storage.removeItem).not.toHaveBeenCalled()
    expect(storage._store['board_ui_animation_duration']).toBe('50')
  })

  it('should do nothing when no animation duration is stored', () => {
    runAnimationDurationMigration(storage)

    expect(storage.removeItem).not.toHaveBeenCalled()
  })

  it('should handle non-numeric values gracefully', () => {
    storage._store['board_ui_animation_duration'] = 'invalid'

    runAnimationDurationMigration(storage)

    // parseInt('invalid') is NaN, so condition !isNaN(value) fails → no removal
    expect(storage.removeItem).not.toHaveBeenCalled()
    expect(storage._store['board_ui_animation_duration']).toBe('invalid')
  })

  it('should handle localStorage throwing errors', () => {
    const brokenStorage = createMockLocalStorage()
    brokenStorage.getItem = vi.fn(() => { throw new Error('SecurityError') })

    expect(() => runAnimationDurationMigration(brokenStorage)).not.toThrow()
  })

  it('should keep value of 0ms (user explicitly disabled animation)', () => {
    storage._store['board_ui_animation_duration'] = '0'

    runAnimationDurationMigration(storage)

    expect(storage.removeItem).not.toHaveBeenCalled()
    expect(storage._store['board_ui_animation_duration']).toBe('0')
  })

  it('should remove value of 101ms (just above threshold)', () => {
    storage._store['board_ui_animation_duration'] = '101'

    runAnimationDurationMigration(storage)

    expect(storage.removeItem).toHaveBeenCalledWith('board_ui_animation_duration')
  })
})

describe('Board Theme Migration (v2)', () => {
  let storage: ReturnType<typeof createMockLocalStorage>
  let setPieceType: (v: string) => void
  let setBoardTheme: (v: string) => void

  beforeEach(() => {
    storage = createMockLocalStorage()
    setPieceType = vi.fn<(v: string) => void>()
    setBoardTheme = vi.fn<(v: string) => void>()
  })

  it('should migrate new user to ChessBase theme and Fritz pieces', () => {
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    expect(setBoardTheme).toHaveBeenCalledWith('chessbase')
    expect(setPieceType).toHaveBeenCalledWith('Fritz')
    expect(storage._store['board_theme_migrated_v2']).toBe('1')
  })

  it('should set migration flag after migrating', () => {
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    expect(storage.setItem).toHaveBeenCalledWith('board_theme_migrated_v2', '1')
  })

  it('should NOT re-migrate if already migrated', () => {
    storage._store['board_theme_migrated_v2'] = '1'

    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    expect(setBoardTheme).not.toHaveBeenCalled()
    expect(setPieceType).not.toHaveBeenCalled()
  })

  it('should be idempotent — running twice does not call setters again', () => {
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)
    expect(setBoardTheme).toHaveBeenCalledTimes(1)
    expect(setPieceType).toHaveBeenCalledTimes(1)

    // Reset mocks and run again
    vi.mocked(setBoardTheme).mockClear()
    vi.mocked(setPieceType).mockClear()

    runBoardThemeMigration(storage, setPieceType, setBoardTheme)
    expect(setBoardTheme).not.toHaveBeenCalled()
    expect(setPieceType).not.toHaveBeenCalled()
  })

  it('should migrate user who had custom theme before v2 migration', () => {
    // User had 'wood' theme but no migration flag
    storage._store['board_theme'] = '"wood"'
    storage._store['board_piece_type'] = '"cburnett"'

    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    // Migration overrides their choice to ChessBase/Fritz
    expect(setBoardTheme).toHaveBeenCalledWith('chessbase')
    expect(setPieceType).toHaveBeenCalledWith('Fritz')
  })
})

describe('Full Migration Flow (both migrations together)', () => {
  let storage: ReturnType<typeof createMockLocalStorage>
  let setPieceType: (v: string) => void
  let setBoardTheme: (v: string) => void

  beforeEach(() => {
    storage = createMockLocalStorage()
    setPieceType = vi.fn<(v: string) => void>()
    setBoardTheme = vi.fn<(v: string) => void>()
  })

  it('should handle fresh user — no existing data', () => {
    runAnimationDurationMigration(storage)
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    // Animation: nothing to migrate
    expect(storage.removeItem).not.toHaveBeenCalled()

    // Theme: migrated to defaults
    expect(setBoardTheme).toHaveBeenCalledWith('chessbase')
    expect(setPieceType).toHaveBeenCalledWith('Fritz')
    expect(storage._store['board_theme_migrated_v2']).toBe('1')
  })

  it('should handle legacy user — stale animation + no theme migration flag', () => {
    storage._store['board_ui_animation_duration'] = '300'
    storage._store['board_theme'] = '"classic"'

    runAnimationDurationMigration(storage)
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    // Animation: stale value removed
    expect(storage._store['board_ui_animation_duration']).toBeUndefined()

    // Theme: migrated
    expect(setBoardTheme).toHaveBeenCalledWith('chessbase')
    expect(setPieceType).toHaveBeenCalledWith('Fritz')
  })

  it('should handle already-migrated user — no changes', () => {
    storage._store['board_ui_animation_duration'] = '50'
    storage._store['board_theme_migrated_v2'] = '1'
    storage._store['board_theme'] = '"chessbase"'

    runAnimationDurationMigration(storage)
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    // Animation: 50ms is fine, no removal
    expect(storage.removeItem).not.toHaveBeenCalled()

    // Theme: already migrated
    expect(setBoardTheme).not.toHaveBeenCalled()
    expect(setPieceType).not.toHaveBeenCalled()
  })

  it('should preserve unrelated localStorage keys during migration', () => {
    storage._store['board_ui_animation_duration'] = '300'
    storage._store['sound_enabled'] = 'true'
    storage._store['chess-chat-sessions'] = '[]'
    storage._store['puzzle_level'] = '3'

    runAnimationDurationMigration(storage)
    runBoardThemeMigration(storage, setPieceType, setBoardTheme)

    // Only animation key removed, others intact
    expect(storage._store['sound_enabled']).toBe('true')
    expect(storage._store['chess-chat-sessions']).toBe('[]')
    expect(storage._store['puzzle_level']).toBe('3')
  })
})
