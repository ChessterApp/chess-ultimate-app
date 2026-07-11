/**
 * @vitest-environment jsdom
 */
import { describe, it, expect } from 'vitest'

import { modelDataToArrayBuffer } from '../storage'

describe('modelDataToArrayBuffer', () => {
  it('returns the ArrayBuffer as-is for the new cache format', async () => {
    const source = new Uint8Array([1, 2, 3, 4]).buffer

    const result = await modelDataToArrayBuffer(source)

    expect(result).toBe(source)
    expect(new Uint8Array(result)).toEqual(new Uint8Array([1, 2, 3, 4]))
  })

  it('converts a legacy Blob cache to an ArrayBuffer', async () => {
    const bytes = new Uint8Array([5, 6, 7, 8])
    const blob = new Blob([bytes])

    const result = await modelDataToArrayBuffer(blob)

    expect(result).toBeInstanceOf(ArrayBuffer)
    expect(new Uint8Array(result)).toEqual(bytes)
  })
})
