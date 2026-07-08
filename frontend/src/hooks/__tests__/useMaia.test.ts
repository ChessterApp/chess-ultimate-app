/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor, act } from '@testing-library/react'

// Controllable singleton state, shared with the mock below.
const ctx = vi.hoisted(() => ({
  state: { status: 'loading' as string, progress: 0, error: null as string | null },
  evaluateMaia3: vi.fn(),
}))

vi.mock('@/lib/engine/maiaSingleton', () => ({
  getMaiaInstance: () => ({ evaluateMaia3: ctx.evaluateMaia3 }),
  getMaiaState: () => ctx.state,
  subscribeMaia: () => () => {},
}))

import { useMaia } from '../useMaia'

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

const serverPolicy = { e2e4: 0.6, d2d4: 0.4 }

beforeEach(() => {
  ctx.state = { status: 'loading', progress: 0, error: null }
  ctx.evaluateMaia3.mockReset()
  vi.restoreAllMocks()
})

describe('useMaia server fallback', () => {
  it('uses the server fallback when the local model is not ready', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ move: 'e2e4', policy: serverPolicy, value: 0.52 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMaia())

    let evaluation: { policy: Record<string, number>; value: number } | null = null
    await act(async () => {
      evaluation = await result.current.evaluatePosition(START_FEN, 1500, 1500)
    })

    expect(fetchMock).toHaveBeenCalledWith('/api/maia/move', expect.objectContaining({ method: 'POST' }))
    expect(evaluation).toEqual({ policy: serverPolicy, value: 0.52 })
    expect(ctx.evaluateMaia3).not.toHaveBeenCalled()
    await waitFor(() => expect(result.current.usingServerFallback).toBe(true))
  })

  it('uses local inference (not the server) once the model is ready', async () => {
    ctx.state = { status: 'ready', progress: 100, error: null }
    ctx.evaluateMaia3.mockResolvedValue({ policy: { g1f3: 1 }, value: 0.5 })
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMaia())
    await waitFor(() => expect(result.current.status).toBe('ready'))

    let evaluation: { policy: Record<string, number>; value: number } | null = null
    await act(async () => {
      evaluation = await result.current.evaluatePosition(START_FEN, 1500, 1500)
    })

    expect(ctx.evaluateMaia3).toHaveBeenCalledOnce()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(evaluation).toEqual({ policy: { g1f3: 1 }, value: 0.5 })
    expect(result.current.usingServerFallback).toBe(false)
  })

  it('falls back to the server if local inference throws', async () => {
    ctx.state = { status: 'ready', progress: 100, error: null }
    ctx.evaluateMaia3.mockRejectedValue(new Error('worker crashed'))
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ move: 'e2e4', policy: serverPolicy, value: 0.52 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMaia())
    await waitFor(() => expect(result.current.status).toBe('ready'))

    let evaluation: { policy: Record<string, number>; value: number } | null = null
    await act(async () => {
      evaluation = await result.current.evaluatePosition(START_FEN, 1500, 1500)
    })

    expect(ctx.evaluateMaia3).toHaveBeenCalledOnce()
    expect(fetchMock).toHaveBeenCalledOnce()
    expect(evaluation).toEqual({ policy: serverPolicy, value: 0.52 })
  })

  it('returns null when both local and server fail', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, status: 500 })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useMaia())

    let evaluation: unknown = 'unset'
    await act(async () => {
      evaluation = await result.current.evaluatePosition(START_FEN, 1500, 1500)
    })

    expect(evaluation).toBeNull()
  })
})
