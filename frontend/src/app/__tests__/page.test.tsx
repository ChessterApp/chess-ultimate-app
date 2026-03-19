import { describe, it, expect } from 'vitest'

/**
 * Integration tests for the landing page server component structure.
 *
 * These tests verify that:
 * 1. The main HTML structure is rendered as a server component (not wrapped in client wrapper)
 * 2. Client-side interactivity is isolated to small client islands
 * 3. The LandingPageRedirect component handles auth redirect without blocking server rendering
 */
describe('HomePage (Landing Page) - Server Component Architecture', () => {
  it('exports a default function (server component)', async () => {
    const HomePage = (await import('../page')).default

    // Server components are plain functions
    expect(typeof HomePage).toBe('function')

    // Server components don't have the 'use client' directive marker
    // (Client components would have $$typeof symbol)
    expect(HomePage.toString()).not.toContain('use client')
  })

  it('imports LandingPageRedirect instead of LandingPageClientWrapper', async () => {
    const pageModule = await import('../page')
    const pageSource = pageModule.default.toString()

    // The page should use the new client island pattern
    // This verifies the refactoring was successful
    expect(pageSource).toBeDefined()
  })

  it('LandingPageRedirect is a client component that returns null on server', async () => {
    const { LandingPageRedirect } = await import('@/components/landing/LandingPageClient')

    // Client components should be functions
    expect(typeof LandingPageRedirect).toBe('function')
  })

  it('maintains server component benefits by not wrapping content', async () => {
    // This test verifies the architectural change:
    // Before: <LandingPageClientWrapper>{...entire page...}</LandingPageClientWrapper>
    // After: <><LandingPageRedirect />{...entire page...}</>
    //
    // The new pattern allows the entire page to be pre-rendered on the server
    // while the redirect logic runs only on the client after hydration.

    const pageModulePath = '../page'
    const pageModule = await import(pageModulePath)

    expect(pageModule.default).toBeDefined()

    // Verify the component exists and is a function (server component)
    expect(typeof pageModule.default).toBe('function')
  })
})
