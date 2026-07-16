/**
 * @vitest-environment jsdom
 *
 * LiveGameEndModal is the online-play result modal — the bot game's
 * celebratory core with an opponent avatar and online actions (Rematch / Back
 * to Play). It reuses GameEndModalBase, so the win/loss/draw layout matches bot
 * games exactly; the online-specific behaviour is the Rematch challenge POST.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest'
import React from 'react'
import { cleanup, render, fireEvent, waitFor } from '@testing-library/react'

const { playSpy, pushSpy, motionState } = vi.hoisted(() => ({
  playSpy: vi.fn(),
  pushSpy: vi.fn(),
  motionState: { reduced: false },
}))

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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushSpy }),
}))

vi.mock('@/components/chess/LottieCelebration', () => ({
  default: () => <div data-testid="lottie-stub" />,
}))

vi.mock('@/hooks/useSoundEffects', () => ({
  useSoundEffects: () => ({ play: playSpy }),
}))

import LiveGameEndModal from '../LiveGameEndModal'

const baseProps = {
  opponentName: 'Alex',
  myColor: 'white' as const,
  initialSec: 300,
  incrementSec: 0,
  open: true,
  onClose: () => {},
}

beforeEach(() => {
  motionState.reduced = false
  playSpy.mockClear()
  pushSpy.mockClear()
})

afterEach(cleanup)

describe('LiveGameEndModal states', () => {
  it('win: confetti + stars + trophy + win title, plays the chime', () => {
    const { getByTestId, queryAllByTestId, container } = render(
      <LiveGameEndModal {...baseProps} outcome="playerWin" />,
    )
    expect(getByTestId('game-end-modal').getAttribute('data-outcome')).toBe('playerWin')
    expect(getByTestId('game-end-confetti')).not.toBeNull()
    expect(queryAllByTestId('game-end-star')).toHaveLength(3)
    expect(container.textContent).toContain('🏆')
    expect(getByTestId('game-end-title').textContent).toBe('winTitle')
    expect(playSpy).toHaveBeenCalledWith('success')
  })

  it('loss: no confetti, encouraging subtitle, opponent name in the loss title', () => {
    const { getByTestId, queryByTestId } = render(
      <LiveGameEndModal {...baseProps} outcome="botWin" />,
    )
    expect(queryByTestId('game-end-confetti')).toBeNull()
    expect(getByTestId('game-end-title').textContent).toBe('lossTitle:Alex')
    expect(getByTestId('game-end-modal').textContent).toContain('lossEncourage')
    expect(playSpy).not.toHaveBeenCalled()
  })

  it('resigned loss uses the resign title', () => {
    const { getByTestId } = render(
      <LiveGameEndModal {...baseProps} outcome="botWin" resigned />,
    )
    expect(getByTestId('game-end-title').textContent).toBe('resignTitle:Alex')
  })

  it('draw: handshake, no bubble, draw title', () => {
    const { getByTestId, queryByTestId, container } = render(
      <LiveGameEndModal {...baseProps} outcome="draw" />,
    )
    expect(queryByTestId('game-end-bubble')).toBeNull()
    expect(container.textContent).toContain('🤝')
    expect(getByTestId('game-end-title').textContent).toBe('drawTitle')
  })

  it('shows the opponent initial-letter avatar on win/loss', () => {
    const { container } = render(<LiveGameEndModal {...baseProps} outcome="botWin" />)
    expect(container.textContent).toContain('A') // first letter of "Alex"
  })
})

describe('LiveGameEndModal actions', () => {
  it('Rematch POSTs a fresh challenge with colors swapped, copies the link, and navigates', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ gameId: 'g2', url: 'https://chesster.io/play/live/g2' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const { getByTestId } = render(<LiveGameEndModal {...baseProps} outcome="botWin" />)
    fireEvent.click(getByTestId('live-end-rematch'))

    await waitFor(() => expect(pushSpy).toHaveBeenCalledWith('/play/live/g2'))

    expect(fetchMock).toHaveBeenCalledWith('/api/games/challenge', expect.any(Object))
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string)
    // White this game → rematch created as black (colors swapped).
    expect(body).toMatchObject({ colorChoice: 'black', initialSec: 300, incrementSec: 0 })
    expect(writeText).toHaveBeenCalledWith('https://chesster.io/play/live/g2')

    vi.unstubAllGlobals()
  })

  it('Rematch surfaces an error and does not navigate when the POST fails', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)

    const { getByTestId, findByTestId } = render(
      <LiveGameEndModal {...baseProps} outcome="draw" />,
    )
    fireEvent.click(getByTestId('live-end-rematch'))

    expect(await findByTestId('live-end-error')).not.toBeNull()
    expect(pushSpy).not.toHaveBeenCalled()

    vi.unstubAllGlobals()
  })

  it('Back to Play navigates to /play', () => {
    const { getByTestId } = render(<LiveGameEndModal {...baseProps} outcome="playerWin" />)
    fireEvent.click(getByTestId('live-end-back'))
    expect(pushSpy).toHaveBeenCalledWith('/play')
  })

  it('X and backdrop dismiss', () => {
    const onClose = vi.fn()
    const { getByTestId } = render(
      <LiveGameEndModal {...baseProps} outcome="draw" onClose={onClose} />,
    )
    fireEvent.click(getByTestId('game-end-close'))
    fireEvent.click(getByTestId('game-end-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('renders nothing when closed', () => {
    const { queryByTestId } = render(
      <LiveGameEndModal {...baseProps} open={false} outcome="playerWin" />,
    )
    expect(queryByTestId('game-end-modal')).toBeNull()
  })
})
