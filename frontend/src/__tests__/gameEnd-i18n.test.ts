/**
 * @vitest-environment node
 */
import { describe, it, expect } from 'vitest'

import en from '../../messages/en.json'
import ru from '../../messages/ru.json'
import kz from '../../messages/kz.json'

const locales: Record<string, { gameEnd?: Record<string, string> }> = { en, ru, kz }

// Every key the GameEndModal reads.
const REQUIRED_KEYS = [
  'winTitle',
  'winBubble',
  'lossTitle',
  'lossBubble',
  'lossEncourage',
  'resignTitle',
  'drawTitle',
  'drawSubtitle',
  'playAgain',
  'rematch',
  'tryStronger',
  'chooseAnother',
  'ariaResult',
]

describe('gameEnd namespace i18n', () => {
  it('exists in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      expect(messages.gameEnd, `gameEnd namespace missing in ${locale}.json`).toBeDefined()
    }
  })

  it('has every required key with a non-empty string in every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const ns = messages.gameEnd ?? {}
      for (const key of REQUIRED_KEYS) {
        expect(typeof ns[key], `${locale}.gameEnd.${key} must be a string`).toBe('string')
        expect(ns[key].trim().length, `${locale}.gameEnd.${key} must not be empty`).toBeGreaterThan(0)
      }
    }
  })

  it('has identical key sets across en / ru / kz', () => {
    const enKeys = Object.keys(en.gameEnd).sort()
    const ruKeys = Object.keys(ru.gameEnd).sort()
    const kzKeys = Object.keys(kz.gameEnd).sort()
    expect(ruKeys).toEqual(enKeys)
    expect(kzKeys).toEqual(enKeys)
  })

  it('preserves the {botName} placeholder in interpolated keys for every locale', () => {
    for (const [locale, messages] of Object.entries(locales)) {
      const ns = messages.gameEnd ?? {}
      for (const key of ['lossTitle', 'resignTitle', 'ariaResult']) {
        expect(ns[key], `${locale}.gameEnd.${key} must interpolate {botName}`).toContain('{botName}')
      }
    }
  })
})
