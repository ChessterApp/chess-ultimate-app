// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import PostHogRouteRecording, { isRecordingAllowed } from '../PostHogRouteRecording'

const { startSessionRecording, stopSessionRecording, nav } = vi.hoisted(() => ({
  startSessionRecording: vi.fn(),
  stopSessionRecording: vi.fn(),
  nav: { pathname: '/' as string | null },
}))
vi.mock('posthog-js', () => ({ default: { startSessionRecording, stopSessionRecording } }))
vi.mock('next/navigation', () => ({ usePathname: () => nav.pathname }))

describe('isRecordingAllowed()', () => {
  it.each(['/', '/onboarding', '/onboarding/step-2', '/upgrade', '/sign-up', '/sign-in/factor-one', '/for-schools', '/for-schools/start/plan'])(
    'allows %s',
    (path) => expect(isRecordingAllowed(path)).toBe(true),
  )

  it.each(['/coach', '/play', '/puzzle/rush', '/profile', '/upgrades', '/sign-input', '/onboardingx', '', null])(
    'blocks %s',
    (path) => expect(isRecordingAllowed(path)).toBe(false),
  )
})

describe('PostHogRouteRecording', () => {
  beforeEach(() => {
    startSessionRecording.mockReset()
    stopSessionRecording.mockReset()
  })

  it('starts recording on an allowlisted route', () => {
    nav.pathname = '/sign-up'
    render(<PostHogRouteRecording />)
    expect(startSessionRecording).toHaveBeenCalledTimes(1)
    expect(stopSessionRecording).not.toHaveBeenCalled()
  })

  it('stops recording when navigating into the app', () => {
    nav.pathname = '/'
    const { rerender } = render(<PostHogRouteRecording />)
    nav.pathname = '/coach'
    rerender(<PostHogRouteRecording />)
    expect(startSessionRecording).toHaveBeenCalledTimes(1)
    expect(stopSessionRecording).toHaveBeenCalledTimes(1)
  })
})
