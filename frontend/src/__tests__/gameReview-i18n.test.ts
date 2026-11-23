/**
 * @vitest-environment node
 *
 * Parity guard for the `gameReview` namespace (Game Review / Game Analysis
 * feature). Mirrors gameEnd-i18n.test.ts but the namespace is nested, so keys
 * are compared after a recursive flatten. Ensures en / ru / kz stay in lockstep:
 * same key set, all non-empty strings, and identical ICU placeholders.
 */
import { describe, it, expect } from 'vitest'

import en from '../../messages/en.json'
import ru from '../../messages/ru.json'
import kz from '../../messages/kz.json'

const locales: Record<string, Record<string, unknown>> = { en, ru, kz }

/** Flatten a nested message object to dot-joined leaf keys → string values. */
function flatten(obj: unknown, prefix = ''): Record<string, string> {
  const out: Record<string, string> = {}
  if (obj && typeof obj === 'object') {
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      const key = prefix ? `${prefix}.${k}` : k
      if (v && typeof v === 'object') Object.assign(out, flatten(v, key))
      else out[key] = String(v)
    }
  }
  return out
}

/** Extract ICU placeholder names, e.g. {san} / {count, plural, ...} → san, count. */
function placeholders(value: string): string[] {
  const names = new Set<string>()
  const re = /\{(\w+)/g
  let m: RegExpExecArray | null
  while ((m = re.exec(value)) !== null) names.add(m[1])
  return [...names].sort()
}

// A representative slice of keys the feature reads at render time — presence of
// these guards against an accidental namespace gutting.
const REQUIRED_KEYS = [
  'header.subtitle',
  'header.toggleTheme',
  'header.failedTitle',
  'header.failedBody',
  'classifications.brilliant',
  'classifications.blunder',
  'classifications.book',
  'classifications.forced',
  'coach.headlines.brilliant',
  'coach.messages.clean',
  'coach.bubblePlaceholder',
  'coach.moveComments.bookLast',
  'coach.moveComments.blunder',
  'coach.moveComments.blunderDropsMaterial',
  'playback.play',
  'playback.pause',
  'playback.next',
  'phases.title',
  'phases.opening',
  'progress.queued',
  'progress.running',
  'startButton.label',
  'startButton.disabledTooltip',
  'panel.startReview',
  'panel.highlights',
  'panel.gameRating',
  'players.white',
  'players.whiteShort',
  'graph.ariaLabel',
]

describe('gameReview namespace i18n', () => {
  it('exists in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      expect(messages.gameReview, `gameReview namespace missing in ${locale}.json`).toBeDefined()
    }
  })

  it('has every required key with a non-empty string in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.gameReview)
      for (const key of REQUIRED_KEYS) {
        expect(typeof flat[key], `${locale}.gameReview.${key} must be a string`).toBe('string')
        expect(
          flat[key]?.trim().length,
          `${locale}.gameReview.${key} must not be empty`,
        ).toBeGreaterThan(0)
      }
    }
  })

  it('has identical (recursively-flattened) key sets across en / ru / kz', () => {
    const enKeys = Object.keys(flatten(en.gameReview)).sort()
    const ruKeys = Object.keys(flatten(ru.gameReview)).sort()
    const kzKeys = Object.keys(flatten(kz.gameReview)).sort()
    expect(ruKeys).toEqual(enKeys)
    expect(kzKeys).toEqual(enKeys)
  })

  it('preserves ICU placeholders identically across every locale', () => {
    const enFlat = flatten(en.gameReview)
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.gameReview)
      for (const [key, value] of Object.entries(enFlat)) {
        expect(
          placeholders(flat[key]),
          `${locale}.gameReview.${key} placeholders must match en`,
        ).toEqual(placeholders(value))
      }
    }
  })

  it('keeps the {san} and {opening} placeholders in the move comments', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const flat = flatten(messages.gameReview)
      expect(flat['coach.moveComments.bookLast'], `${locale} bookLast {san}`).toContain('{san}')
      expect(flat['coach.moveComments.bookLast'], `${locale} bookLast {opening}`).toContain(
        '{opening}',
      )
      expect(flat['coach.messages.clean'], `${locale} clean {accuracy}`).toContain('{accuracy}')
    }
  })
})
