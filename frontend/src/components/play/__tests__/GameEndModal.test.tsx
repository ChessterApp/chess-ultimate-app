/**
 * @vitest-environment jsdom
 *
 * GameEndModal is the "Variation B" celebratory result modal. It themes itself
 * per bot via gameTheme(), shows confetti + stars on a win, an encouraging
 * bounce on a loss, and a neutral handshake card on a draw.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import React from 'react'
import { cleanup, render, fireEvent } from '@testing-library/react'

const { playSpy, motionState } = vi.hoisted(() => ({
  playSpy: vi.fn(),
  motionState: { reduced: false },
}))

// Keep real motion components but drive prefers-reduced-motion deterministically
// (framer-motion's own hook resolves to `false` on the first jsdom render).
vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<typeof import('framer-motion')>()
  return { ...actual, useReducedMotion: () => motionState.reduced }
})

// Echo keys (interpolating botName) so assertions can target exact keys.
vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (key: string, values?: Record<string, string | number>) =>
      values?.botName !== undefined ? `${key}:${values.botName}` : key
    t.has = () => true
    return t
  },
}))

vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}))

// Avoid loading the dotLottie WASM player in jsdom.
vi.mock('@/components/chess/LottieCelebration', () => ({
  default: () => <div data-testid="lottie-stub" />,
}))

vi.mock('@/hooks/useSoundEffects', () => ({
  useSoundEffects: () => ({ play: playSpy }),
}))

import GameEndModal from '../GameEndModal'
import { BOTS } from '@/data/bots'

const firstBot = BOTS[0]
const lastBot = BOTS[BOTS.length - 1]

beforeEach(() => {
  motionState.reduced = false
  playSpy.mockClear()
})

afterEach(cleanup)

const baseProps = {
  bot: firstBot,
  open: true,
  onClose: () => {},
  onPlayAgain: () => {},
  onTryStronger: () => {},
  onChooseAnother: () => {},
}

describe('GameEndModal variants', () => {
  it('renders nothing when closed', () => {
    const { queryByTestId } = render(
      <GameEndModal {...baseProps} open={false} outcome="playerWin" />,
    )
    expect(queryByTestId('game-end-modal')).toBeNull()
  })

  it('win: shows confetti, stars, trophy and the win title', () => {
    const { getByTestId, queryAllByTestId, container } = render(
      <GameEndModal {...baseProps} outcome="playerWin" />,
    )
    expect(getByTestId('game-end-modal').getAttribute('data-outcome')).toBe('playerWin')
    expect(getByTestId('game-end-confetti')).not.toBeNull()
    expect(queryAllByTestId('game-end-star')).toHaveLength(3)
    expect(container.textContent).toContain('🏆')
    expect(getByTestId('game-end-title').textContent).toBe('winTitle')
  })

  it('loss: shows NO confetti, an encouraging subtitle and the loss title', () => {
    const { getByTestId, queryByTestId } = render(
      <GameEndModal {...baseProps} outcome="botWin" />,
    )
    expect(queryByTestId('game-end-confetti')).toBeNull()
    expect(queryByTestId('game-end-star')).toBeNull()
    expect(getByTestId('game-end-title').textContent).toBe(`lossTitle:${firstBot.name}`)
    expect(getByTestId('game-end-modal').textContent).toContain('lossEncourage')
  })

  it('resigned loss uses the resign title, not the checkmate loss title', () => {
    const { getByTestId } = render(
      <GameEndModal {...baseProps} outcome="botWin" resigned />,
    )
    expect(getByTestId('game-end-title').textContent).toBe(`resignTitle:${firstBot.name}`)
  })

  it('draw: neutral card with handshake, no confetti and no avatar bubble', () => {
    const { getByTestId, queryByTestId, container } = render(
      <GameEndModal {...baseProps} outcome="draw" />,
    )
    expect(queryByTestId('game-end-confetti')).toBeNull()
    expect(queryByTestId('game-end-bubble')).toBeNull()
    expect(container.textContent).toContain('🤝')
    expect(getByTestId('game-end-title').textContent).toBe('drawTitle')
  })
})

describe('GameEndModal sound', () => {
  it('plays the win chime on a win only', () => {
    render(<GameEndModal {...baseProps} outcome="playerWin" />)
    expect(playSpy).toHaveBeenCalledWith('success')
  })

  it('is silent on a loss', () => {
    render(<GameEndModal {...baseProps} outcome="botWin" />)
    expect(playSpy).not.toHaveBeenCalled()
  })

  it('is silent on a draw', () => {
    render(<GameEndModal {...baseProps} outcome="draw" />)
    expect(playSpy).not.toHaveBeenCalled()
  })
})

describe('GameEndModal actions', () => {
  it('primary button fires onPlayAgain (Play again / Rematch)', () => {
    const onPlayAgain = vi.fn()
    const { getByTestId } = render(
      <GameEndModal {...baseProps} outcome="playerWin" onPlayAgain={onPlayAgain} />,
    )
    fireEvent.click(getByTestId('game-end-primary'))
    expect(onPlayAgain).toHaveBeenCalledTimes(1)
  })

  it('Try a stronger bot selects the next bot in BOTS order', () => {
    const onTryStronger = vi.fn()
    const { getByTestId } = render(
      <GameEndModal {...baseProps} outcome="playerWin" onTryStronger={onTryStronger} />,
    )
    fireEvent.click(getByTestId('game-end-secondary'))
    expect(onTryStronger).toHaveBeenCalledWith(BOTS[1])
  })

  it('hides Try a stronger bot on the last bot', () => {
    const { queryByTestId } = render(
      <GameEndModal {...baseProps} bot={lastBot} outcome="playerWin" />,
    )
    expect(queryByTestId('game-end-secondary')).toBeNull()
  })

  it('Choose another bot fires onChooseAnother on a loss', () => {
    const onChooseAnother = vi.fn()
    const { getByTestId } = render(
      <GameEndModal {...baseProps} outcome="botWin" onChooseAnother={onChooseAnother} />,
    )
    fireEvent.click(getByTestId('game-end-secondary'))
    expect(onChooseAnother).toHaveBeenCalledTimes(1)
  })

  it('X button and backdrop both dismiss', () => {
    const onClose = vi.fn()
    const { getByTestId } = render(
      <GameEndModal {...baseProps} outcome="draw" onClose={onClose} />,
    )
    fireEvent.click(getByTestId('game-end-close'))
    fireEvent.click(getByTestId('game-end-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(2)
  })
})

describe('GameEndModal accessibility', () => {
  it('exposes an assertive live region announcing the result', () => {
    const { container } = render(<GameEndModal {...baseProps} outcome="playerWin" />)
    const live = container.querySelector('[aria-live="assertive"]')
    expect(live).not.toBeNull()
    expect(live?.textContent).toBe(`ariaResult:${firstBot.name}`)
  })

  it('is a labelled modal dialog', () => {
    const { getByTestId } = render(<GameEndModal {...baseProps} outcome="draw" />)
    const modal = getByTestId('game-end-modal')
    expect(modal.getAttribute('role')).toBe('dialog')
    expect(modal.getAttribute('aria-modal')).toBe('true')
  })
})

describe('GameEndModal reduced motion', () => {
  it('renders the static card without confetti under prefers-reduced-motion', () => {
    motionState.reduced = true
    const { getByTestId, queryByTestId } = render(
      <GameEndModal {...baseProps} outcome="playerWin" />,
    )
    // Content is identical (title + stars still present) but confetti is skipped.
    expect(getByTestId('game-end-modal')).not.toBeNull()
    expect(getByTestId('game-end-title').textContent).toBe('winTitle')
    expect(queryByTestId('game-end-confetti')).toBeNull()
  })
})
