import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Stockfish16 } from '../Stockfish16'

// Mock WebAssembly globals
const mockValidate = vi.fn()
const mockCompile = vi.fn()
const mockInstantiate = vi.fn()

beforeEach(() => {
  vi.clearAllMocks()
  // @ts-expect-error - mocking global
  globalThis.WebAssembly = {
    validate: mockValidate,
    compile: mockCompile,
    instantiate: mockInstantiate,
  }
})

describe('Stockfish16.isSupported', () => {
  it('returns false when WebAssembly is not available', () => {
    // @ts-expect-error - mocking global
    globalThis.WebAssembly = undefined
    expect(Stockfish16.isSupported()).toBe(false)
  })

  it('returns false when basic WASM validation fails', () => {
    mockValidate.mockReturnValue(false)
    expect(Stockfish16.isSupported()).toBe(false)
  })

  it('returns true when both basic WASM and SIMD validation pass', () => {
    mockValidate.mockReturnValue(true)
    expect(Stockfish16.isSupported()).toBe(true)
  })

  it('returns false when SIMD validation fails (second call)', () => {
    mockValidate.mockReturnValueOnce(true).mockReturnValueOnce(false)
    expect(Stockfish16.isSupported()).toBe(false)
  })
})

describe('Stockfish16.smokeTestSimd', () => {
  it('returns false when isSupported returns false', async () => {
    mockValidate.mockReturnValue(false)
    const result = await Stockfish16.smokeTestSimd()
    expect(result).toBe(false)
  })

  it('returns true when WASM module compiles and executes successfully', async () => {
    mockValidate.mockReturnValue(true)

    const mockExports = { t: vi.fn() }
    const mockModule = {}
    mockCompile.mockResolvedValue(mockModule)
    mockInstantiate.mockResolvedValue({ exports: mockExports })

    const result = await Stockfish16.smokeTestSimd()
    expect(result).toBe(true)
    expect(mockExports.t).toHaveBeenCalled()
  })

  it('returns false when WASM compilation fails', async () => {
    mockValidate.mockReturnValue(true)
    mockCompile.mockRejectedValue(new Error('CompileError'))

    const result = await Stockfish16.smokeTestSimd()
    expect(result).toBe(false)
  })

  it('returns false when WASM instantiation fails', async () => {
    mockValidate.mockReturnValue(true)
    mockCompile.mockResolvedValue({})
    mockInstantiate.mockRejectedValue(new Error('LinkError'))

    const result = await Stockfish16.smokeTestSimd()
    expect(result).toBe(false)
  })

  it('returns false when WASM execution throws (SIGILL scenario)', async () => {
    mockValidate.mockReturnValue(true)
    mockCompile.mockResolvedValue({})
    mockInstantiate.mockResolvedValue({
      exports: {
        t: () => { throw new Error('RuntimeError: unreachable') }
      }
    })

    const result = await Stockfish16.smokeTestSimd()
    expect(result).toBe(false)
  })
})
