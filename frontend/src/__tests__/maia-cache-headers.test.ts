import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

/**
 * Phase 4 (persistence hardening): the Maia model (/maia3/) and the ORT runtime
 * (/ort/) must be served immutable + long-lived so the ~24MB download survives
 * revisits and deploys. Asserted against the source of next.config.ts.
 */
describe('Maia / ORT cache headers', () => {
  const config = readFileSync(
    resolve(__dirname, '../../next.config.ts'),
    'utf-8',
  )

  const IMMUTABLE = "public, max-age=31536000, immutable"

  function ruleBlock(source: string): string {
    // Grab the text of the header rule object for a given `source:` selector.
    const idx = config.indexOf(`source: '${source}'`)
    expect(idx, `header rule for ${source} should exist`).toBeGreaterThan(-1)
    return config.slice(idx, idx + 800)
  }

  it('serves the Maia model immutable for a year', () => {
    expect(ruleBlock('/maia3/:path*')).toContain(IMMUTABLE)
  })

  it('serves the ORT runtime immutable for a year', () => {
    expect(ruleBlock('/ort/:path*')).toContain(IMMUTABLE)
  })

  it('keeps the CORP header on the Maia model rule', () => {
    expect(ruleBlock('/maia3/:path*')).toContain('Cross-Origin-Resource-Policy')
  })
})
