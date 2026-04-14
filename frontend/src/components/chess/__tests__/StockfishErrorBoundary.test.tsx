/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { StockfishErrorBoundary } from '../StockfishErrorBoundary'

// A component that throws during render
function ThrowingComponent({ error }: { error: Error }) {
  throw error
}

describe('StockfishErrorBoundary', () => {
  // Suppress console.error from React's error boundary logging
  const originalError = console.error
  beforeEach(() => {
    console.error = vi.fn()
  })
  afterEach(() => {
    console.error = originalError
  })

  it('renders children normally when no error occurs', () => {
    render(
      <StockfishErrorBoundary>
        <div>Chess engine works</div>
      </StockfishErrorBoundary>
    )
    expect(screen.getByText('Chess engine works')).toBeTruthy()
  })

  it('renders default fallback when child throws', () => {
    render(
      <StockfishErrorBoundary>
        <ThrowingComponent error={new Error('WASM SIGILL')} />
      </StockfishErrorBoundary>
    )
    expect(screen.getByText('Chess engine is not available on this device')).toBeTruthy()
  })

  it('renders custom fallback when provided', () => {
    render(
      <StockfishErrorBoundary fallback={<div>Custom error message</div>}>
        <ThrowingComponent error={new Error('crash')} />
      </StockfishErrorBoundary>
    )
    expect(screen.getByText('Custom error message')).toBeTruthy()
  })
})
