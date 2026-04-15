import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Stockfish17 } from '../Stockfish17'

const mockValidate = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  // @ts-expect-error - mocking global
  globalThis.WebAssembly = {
    validate: mockValidate,
  }
})

describe('Stockfish17.isSupported', () => {
  it('returns false when WebAssembly is not available', () => {
    // @ts-expect-error - mocking global
    globalThis.WebAssembly = undefined
    expect(Stockfish17.isSupported()).toBe(false)
  })

  it('returns false when basic WASM validation fails', () => {
    mockValidate.mockReturnValue(false)
    expect(Stockfish17.isSupported()).toBe(false)
  })

  it('returns true when both basic WASM and SIMD validation pass', () => {
    mockValidate.mockReturnValue(true)
    expect(Stockfish17.isSupported()).toBe(true)
  })

  it('returns false when SIMD validation fails (second call)', () => {
    mockValidate.mockReturnValueOnce(true).mockReturnValueOnce(false)
    expect(Stockfish17.isSupported()).toBe(false)
  })

  it('calls WebAssembly.validate with SIMD bytecode', () => {
    mockValidate.mockReturnValue(true)
    Stockfish17.isSupported()

    expect(mockValidate).toHaveBeenCalledTimes(2)
    // Second call should be the SIMD check with v128 opcodes
    const simdArg = mockValidate.mock.calls[1][0]
    expect(simdArg).toBeInstanceOf(Uint8Array)
    // SIMD bytecode starts with WASM magic bytes
    expect(simdArg[0]).toBe(0)
    expect(simdArg[1]).toBe(97)  // 'a'
    expect(simdArg[2]).toBe(115) // 's'
    expect(simdArg[3]).toBe(109) // 'm'
  })
})
