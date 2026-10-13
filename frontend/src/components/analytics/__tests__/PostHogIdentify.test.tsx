// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import PostHogIdentify from '../PostHogIdentify'

const { identify, reset, capture, auth, clerkUser } = vi.hoisted(() => ({
  identify: vi.fn(),
  reset: vi.fn(),
  capture: vi.fn(),
  auth: { isLoaded: true, userId: null as string | null },
  clerkUser: { value: null as Record<string, unknown> | null },
}))
vi.mock('posthog-js', () => ({ default: { identify, reset, capture } }))
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => auth,
  useUser: () => ({ user: clerkUser.value }),
}))

function setAuth(isLoaded: boolean, userId: string | null) {
  auth.isLoaded = isLoaded
  auth.userId = userId
}

describe('PostHogIdentify', () => {
  beforeEach(() => {
    identify.mockReset()
    reset.mockReset()
    capture.mockReset()
    clerkUser.value = null
    localStorage.clear()
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

  describe('client user_signed_up', () => {
    const fresh = (over: Record<string, unknown> = {}) => ({
      id: 'user_new',
      createdAt: new Date(Date.now() - 60_000),
      externalAccounts: [{ provider: 'google' }],
      primaryEmailAddressId: 'e1',
      ...over,
    })

    it('fires once per device for a brand-new account, after identify', () => {
      setAuth(true, 'user_new')
      clerkUser.value = fresh()
      const { rerender } = render(<PostHogIdentify />)
      expect(capture).toHaveBeenCalledWith('user_signed_up', {
        method: 'google',
        signup_source: 'client',
      })
      expect(identify.mock.invocationCallOrder[0]).toBeLessThan(capture.mock.invocationCallOrder[0])
      clerkUser.value = fresh()
      rerender(<PostHogIdentify />)
      expect(capture).toHaveBeenCalledTimes(1)
    })

    it('does not fire for an existing account signing in', () => {
      setAuth(true, 'user_new')
      clerkUser.value = fresh({ createdAt: new Date(Date.now() - 86_400_000) })
      render(<PostHogIdentify />)
      expect(capture).not.toHaveBeenCalled()
    })

    it('derives email when there is no Google account', () => {
      setAuth(true, 'user_new')
      clerkUser.value = fresh({ externalAccounts: [] })
      render(<PostHogIdentify />)
      expect(capture.mock.calls[0][1]).toMatchObject({ method: 'email' })
    })
  })
})
