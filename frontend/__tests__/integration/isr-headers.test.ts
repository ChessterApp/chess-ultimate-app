import { describe, it, expect } from 'vitest'

/**
 * Integration tests for ISR headers configuration
 * These tests verify that the headers are correctly configured for pages using ISR
 */

describe('ISR Headers Integration', () => {
  it('should export revalidate constant from landing page', async () => {
    // Import the landing page module
    const landingPage = await import('../../src/app/page')

    // Verify revalidate is exported
    expect(landingPage.revalidate).toBeDefined()
    expect(typeof landingPage.revalidate).toBe('number')
    expect(landingPage.revalidate).toBe(3600) // 1 hour
  })

  it('should have matching cache header for landing page ISR config', async () => {
    const config = await import('../../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()
    const isrHeader = headers.find((h: any) => h.source === '/')
    const cacheControl = isrHeader.headers.find((h: any) => h.key === 'Cache-Control')

    // Extract s-maxage value
    const match = cacheControl.value.match(/s-maxage=(\d+)/)
    const sMaxAge = parseInt(match[1], 10)

    // Import the landing page to get the actual revalidate value
    const landingPage = await import('../../src/app/page')

    // They should match
    expect(sMaxAge).toBe(landingPage.revalidate)
  })

  it('should use public cache for ISR pages', async () => {
    const config = await import('../../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()
    const isrHeader = headers.find((h: any) => h.source === '/')
    const cacheControl = isrHeader.headers.find((h: any) => h.key === 'Cache-Control')

    expect(cacheControl.value).toContain('public')
  })

  it('should configure stale-while-revalidate for resilience', async () => {
    const config = await import('../../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()
    const isrHeader = headers.find((h: any) => h.source === '/')
    const cacheControl = isrHeader.headers.find((h: any) => h.key === 'Cache-Control')

    expect(cacheControl.value).toContain('stale-while-revalidate')

    // Extract the value
    const match = cacheControl.value.match(/stale-while-revalidate=(\d+)/)
    expect(match).toBeTruthy()

    const swr = parseInt(match[1], 10)

    // Should be at least equal to revalidate time for proper fallback
    const landingPage = await import('../../src/app/page')
    expect(swr).toBeGreaterThanOrEqual(landingPage.revalidate)
  })

  it('should not conflict with global security headers', async () => {
    const config = await import('../../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()

    // Get both header sets
    const globalHeaders = headers.find((h: any) => h.source === '/:path*')
    const isrHeaders = headers.find((h: any) => h.source === '/')

    // Both should exist
    expect(globalHeaders).toBeDefined()
    expect(isrHeaders).toBeDefined()

    // ISR headers should not duplicate security headers
    const isrHeaderKeys = isrHeaders.headers.map((h: any) => h.key)
    expect(isrHeaderKeys).not.toContain('X-Frame-Options')
    expect(isrHeaderKeys).not.toContain('X-Content-Type-Options')
    expect(isrHeaderKeys).not.toContain('Content-Security-Policy')

    // Only Cache-Control should be in ISR headers
    expect(isrHeaderKeys).toContain('Cache-Control')
    expect(isrHeaderKeys.length).toBe(1)
  })
})
