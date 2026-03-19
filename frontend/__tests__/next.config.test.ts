import { describe, it, expect, vi } from 'vitest'

// Mock the next-intl plugin
const mockWithNextIntl = (config: any) => config

vi.mock('next-intl/plugin', () => ({
  default: () => mockWithNextIntl,
}))

describe('next.config.ts', () => {
  it('should include ISR cache headers for the landing page', async () => {
    // Dynamically import the config
    const config = await import('../next.config')
    const nextConfig = config.default

    // Get the headers
    const headers = await nextConfig.headers()

    // Find the ISR header rule
    const isrHeader = headers.find((h: any) => h.source === '/')

    expect(isrHeader).toBeDefined()
    expect(isrHeader.headers).toBeDefined()

    const cacheControl = isrHeader.headers.find((h: any) => h.key === 'Cache-Control')
    expect(cacheControl).toBeDefined()
    expect(cacheControl.value).toBe('public, s-maxage=3600, stale-while-revalidate=7200')
  })

  it('should include security headers for all routes', async () => {
    const config = await import('../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()

    // Find the global security header rule
    const securityHeader = headers.find((h: any) => h.source === '/:path*')

    expect(securityHeader).toBeDefined()
    expect(securityHeader.headers).toBeDefined()

    const headerKeys = securityHeader.headers.map((h: any) => h.key)
    expect(headerKeys).toContain('X-Frame-Options')
    expect(headerKeys).toContain('X-Content-Type-Options')
    expect(headerKeys).toContain('Content-Security-Policy')
  })

  it('should include COEP headers for chess engine pages', async () => {
    const config = await import('../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()

    // Find the engine pages
    const gameHeader = headers.find((h: any) => h.source === '/game/:path*')
    const positionHeader = headers.find((h: any) => h.source === '/position/:path*')
    const puzzleHeader = headers.find((h: any) => h.source === '/puzzle/:path*')

    expect(gameHeader).toBeDefined()
    expect(positionHeader).toBeDefined()
    expect(puzzleHeader).toBeDefined()

    const headerKeys = gameHeader.headers.map((h: any) => h.key)
    expect(headerKeys).toContain('Cross-Origin-Embedder-Policy')
    expect(headerKeys).toContain('Cross-Origin-Opener-Policy')
  })

  it('should have ISR cache time match the revalidate period', async () => {
    const config = await import('../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()
    const isrHeader = headers.find((h: any) => h.source === '/')
    const cacheControl = isrHeader.headers.find((h: any) => h.key === 'Cache-Control')

    // Extract s-maxage value
    const match = cacheControl.value.match(/s-maxage=(\d+)/)
    expect(match).toBeTruthy()

    const sMaxAge = parseInt(match[1], 10)

    // Should match the revalidate value in src/app/page.tsx (3600 seconds)
    expect(sMaxAge).toBe(3600)
  })

  it('should have stale-while-revalidate longer than cache time', async () => {
    const config = await import('../next.config')
    const nextConfig = config.default

    const headers = await nextConfig.headers()
    const isrHeader = headers.find((h: any) => h.source === '/')
    const cacheControl = isrHeader.headers.find((h: any) => h.key === 'Cache-Control')

    // Extract both values
    const sMaxAgeMatch = cacheControl.value.match(/s-maxage=(\d+)/)
    const swrMatch = cacheControl.value.match(/stale-while-revalidate=(\d+)/)

    expect(sMaxAgeMatch).toBeTruthy()
    expect(swrMatch).toBeTruthy()

    const sMaxAge = parseInt(sMaxAgeMatch[1], 10)
    const swr = parseInt(swrMatch[1], 10)

    // stale-while-revalidate should be longer than s-maxage
    expect(swr).toBeGreaterThan(sMaxAge)
  })
})
