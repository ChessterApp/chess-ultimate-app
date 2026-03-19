/**
 * Test to verify ISR configuration on landing page
 */

import { describe, it, expect } from 'vitest'

describe('Landing Page ISR Configuration', () => {
  it('should export revalidate constant with value 3600', async () => {
    // Dynamic import to access the named export
    const pageModule = await import('../page')

    expect(pageModule).toHaveProperty('revalidate')
    expect(pageModule.revalidate).toBe(3600)
  })

  it('should have revalidate set to one hour in seconds', async () => {
    const pageModule = await import('../page')
    const ONE_HOUR_IN_SECONDS = 60 * 60

    expect(pageModule.revalidate).toBe(ONE_HOUR_IN_SECONDS)
  })
})
