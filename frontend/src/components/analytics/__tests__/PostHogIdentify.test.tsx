// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import PostHogIdentify from '../PostHogIdentify'

const { identify, reset, auth } = vi.hoisted(() => ({
  identify: vi.fn(),
  reset: vi.fn(),
  auth: { isLoaded: true, userId: null as string | null },
}))
vi.mock('posthog-js', () => ({ default: { identify, reset } }))
vi.mock('@clerk/nextjs', () => ({ useAuth: () => auth }))

function setAuth(isLoaded: boolean, userId: string | null) {
  auth.isLoaded = isLoaded
  auth.userId = userId
}

describe('PostHogIdentify', () => {
  beforeEach(() => {
    identify.mockReset()
    reset.mockReset()
    setAuth(true, null)
  })

  it('identifies with the Clerk user id only', () => {
    setAuth(true, 'user_123')
    render(<PostHogIdentify />)
    expect(identify).toHaveBeenCalledTimes(1)
    expect(identify).toHaveBeenCalledWith('user_123')
    expect(reset).not.toHaveBeenCalled()
  })

  it('does nothing for an anonymous visitor', () => {
    render(<PostHogIdentify />)
    expect(identify).not.toHaveBeenCalled()
    expect(reset).not.toHaveBeenCalled()
  })

  it('waits for Clerk to load', () => {
    setAuth(false, null)
    const { rerender } = render(<PostHogIdentify />)
    expect(identify).not.toHaveBeenCalled()
    setAuth(true, 'user_123')
    rerender(<PostHogIdentify />)
    expect(identify).toHaveBeenCalledWith('user_123')
  })

  it('resets when the user signs out', () => {
    setAuth(true, 'user_123')
    const { rerender } = render(<PostHogIdentify />)
    setAuth(true, null)
    rerender(<PostHogIdentify />)
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('identifies the new user after a sign-out/sign-in switch', () => {
    setAuth(true, 'user_a')
    const { rerender } = render(<PostHogIdentify />)
    setAuth(true, null)
    rerender(<PostHogIdentify />)
    setAuth(true, 'user_b')
    rerender(<PostHogIdentify />)
    expect(identify.mock.calls).toEqual([['user_a'], ['user_b']])
    expect(reset).toHaveBeenCalledTimes(1)
  })

  it('does not re-identify on re-render with the same user', () => {
    setAuth(true, 'user_123')
    const { rerender } = render(<PostHogIdentify />)
    rerender(<PostHogIdentify />)
    expect(identify).toHaveBeenCalledTimes(1)
  })
})
