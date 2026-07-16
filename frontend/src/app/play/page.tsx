'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Chess } from 'chess.js'
import { Box, Alert } from '@mui/material'
import { useReducedMotion } from 'framer-motion'
import { useTranslations } from 'next-intl'
import ChessgroundBoard from '@/components/chess/ChessgroundBoard'
import BotGrid from '@/components/play/BotGrid'
import PlayFriendCard from '@/components/play/PlayFriendCard'
import { ONLINE_PLAY_ENABLED } from '@/lib/feature-flags'
import GameSetup from '@/components/play/GameSetup'
import GameHeader from '@/components/play/GameHeader'
import GameDock from '@/components/play/GameDock'
import GameEndModal from '@/components/play/GameEndModal'
import { outcomeFromPosition, type GameOutcome } from '@/lib/gameOutcome'
import { useMaia } from '@/hooks/useMaia'
import { useStockfishPlay } from '@/hooks/useStockfishPlay'
import { usePhaseHistory } from '@/hooks/usePhaseHistory'
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events'
import { playText } from '@/lib/botI18n'
import { fredoka } from '@/lib/fonts'
import type { Bot } from '@/data/bots'
import { gameTheme, getBotById } from '@/data/bots'
import type { Key } from 'chessground/types'

// Import chessground CSS
import 'chessground/assets/chessground.base.css'
import 'chessground/assets/chessground.brown.css'
import '@/styles/chessground-theme.css'

type GamePhase = 'selecting' | 'setup' | 'playing' | 'ended'
type PlayerColor = 'white' | 'black' | 'random'

// Phase + selected bot, mirrored to `/play?phase=…&bot=…` history entries.
interface PlayPhaseState {
  phase: GamePhase
  bot: string | null
}

// Temperature-based move selection
function selectMove(
  moveProbs: Record<string, number>,
  temperature: number = 1.0,
): string {
  const moves = Object.keys(moveProbs)
  const probs = moves.map((m) => moveProbs[m])

  // Apply temperature
  const scaled = probs.map((p) => Math.pow(p, 1 / temperature))
  const sum = scaled.reduce((a, b) => a + b, 0)
  const normalized = scaled.map((p) => p / sum)

  // Weighted random selection
  let r = Math.random()
  for (let i = 0; i < moves.length; i++) {
    r -= normalized[i]
    if (r <= 0) return moves[i]
  }
  return moves[moves.length - 1]
}

export default function PlayPage() {
  const t = useTranslations('bots')
  const { status, error, evaluatePosition, downloadModel, usingServerFallback } =
    useMaia()
  const stockfishPlay = useStockfishPlay()

  // Regression guard: track (once per game) when a bot move is needed before the
  // local engine is ready, so a spike is visible in analytics.
  const engineWaitTracked = useRef(false)

  // Setup state
  const [selectedBot, setSelectedBot] = useState<Bot | null>(null)
  const [playerColor, setPlayerColor] = useState<PlayerColor>('white')
  const [gamePhase, setGamePhase] = useState<GamePhase>('selecting')

  // Game state
  const [chess] = useState(new Chess())
  const [fen, setFen] = useState(chess.fen())
  const [actualPlayerColor, setActualPlayerColor] = useState<'w' | 'b'>('w')
  const [gameResult, setGameResult] = useState<string | null>(null)
  // Structured outcome (player POV) driving the celebratory result modal. Kept
  // alongside the plain `gameResult` string, which still powers the dock.
  const [gameOutcome, setGameOutcome] = useState<GameOutcome | null>(null)
  const [resigned, setResigned] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [thinking, setThinking] = useState(false)
  const [lastMove, setLastMove] = useState<[Key, Key] | undefined>(undefined)
  const [playerCanMove, setPlayerCanMove] = useState(true)
  const prefersReducedMotion = useReducedMotion()

  // Bot-move cancellation: the pending "thinking" setTimeout and a generation
  // counter that invalidates any in-flight makeBotMove. When the user leaves
  // the game (Back button → popstate), cancelBotWork() clears both so no stale
  // move fires or mutates state after we've left the board.
  const botMoveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const moveGeneration = useRef(0)

  const cancelBotWork = () => {
    if (botMoveTimer.current) {
      clearTimeout(botMoveTimer.current)
      botMoveTimer.current = null
    }
    moveGeneration.current += 1
    setThinking(false)
  }

  const scheduleBotMove = () => {
    if (botMoveTimer.current) clearTimeout(botMoveTimer.current)
    botMoveTimer.current = setTimeout(() => {
      botMoveTimer.current = null
      makeBotMove()
    }, 500)
  }

  // Auto-download model when not cached
  const downloadTriggered = useRef(false)

  useEffect(() => {
    if (status === 'no-cache' && !downloadTriggered.current) {
      downloadTriggered.current = true
      downloadModel().catch((err) => console.error('Auto-download failed:', err))
    }
  }, [status, downloadModel])

  // Reveal the result modal ~0.8s after the game ends so the final position is
  // visible first. Reduced-motion users skip the deliberate delay.
  useEffect(() => {
    if (gamePhase !== 'ended' || !gameOutcome) {
      setModalOpen(false)
      return
    }
    const delay = prefersReducedMotion ? 0 : 800
    const timer = setTimeout(() => setModalOpen(true), delay)
    return () => clearTimeout(timer)
  }, [gamePhase, gameOutcome, prefersReducedMotion])

  // Rebuild the screen from a URL phase, on mount (refresh/deep-link) and on
  // popstate (Back/Forward). A live game can't be restored from the URL alone,
  // so `playing`/`ended` land on `setup` for the selected bot instead of a hard
  // reset to `selecting`. Any pending bot move is cancelled whenever we land
  // anywhere other than `playing`.
  const restoreFromUrl = (target: PlayPhaseState, replace: (p: PlayPhaseState) => void) => {
    const bot = target.bot ? getBotById(target.bot) ?? null : null

    if (target.phase !== 'playing') cancelBotWork()

    if ((target.phase === 'setup' || target.phase === 'playing' || target.phase === 'ended') && bot) {
      setSelectedBot(bot)
      setGamePhase('setup')
      setGameResult(null)
      setGameOutcome(null)
      // Correct the URL in place (no new entry) when downgrading playing/ended.
      if (target.phase !== 'setup') replace({ phase: 'setup', bot: bot.id })
      return
    }

    // selecting (or a phase whose bot no longer exists)
    setSelectedBot(null)
    setGamePhase('selecting')
    setGameResult(null)
    setGameOutcome(null)
  }

  const history = usePhaseHistory<PlayPhaseState>({
    parse: (params) => ({
      phase: (params.get('phase') as GamePhase) || 'selecting',
      bot: params.get('bot'),
    }),
    serialize: (p) => ({ phase: p.phase, bot: p.bot }),
    onRestore: (phase, meta) => restoreFromUrl(phase, meta.replace),
  })

  const handleBotSelect = (bot: Bot) => {
    setSelectedBot(bot)
    setGamePhase('setup')
    history.push({ phase: 'setup', bot: bot.id })
  }

  const handleChangeBot = () => {
    // Mirror the Back button: pop the `setup` entry back to `selecting`.
    history.back()
  }

  const startGame = (bot: Bot | null = selectedBot) => {
    if (!bot) return
    setSelectedBot(bot)

    // Determine actual player color
    let actualColor: 'w' | 'b' = 'w'
    if (playerColor === 'random') {
      actualColor = Math.random() < 0.5 ? 'w' : 'b'
    } else {
      actualColor = playerColor === 'white' ? 'w' : 'b'
    }

    // Fresh game: drop any pending bot work from a previous one.
    cancelBotWork()
    setActualPlayerColor(actualColor)
    chess.reset()
    setFen(chess.fen())
    setGameResult(null)
    setGameOutcome(null)
    setResigned(false)
    setModalOpen(false)
    setGamePhase('playing')
    setLastMove(undefined)
    engineWaitTracked.current = false
    history.push({ phase: 'playing', bot: bot.id })

    // If player is black, bot moves first
    if (actualColor === 'b') {
      setPlayerCanMove(false)
      scheduleBotMove()
    } else {
      setPlayerCanMove(true)
    }
  }

  const makeBotMove = async () => {
    if (chess.isGameOver() || !selectedBot) {
      checkGameOver()
      return
    }

    // Snapshot the generation so a move started before a Back-nav is discarded
    // instead of mutating the board after we've left the game.
    const generation = moveGeneration.current
    setThinking(true)
    try {
      const currentFen = chess.fen()
      let selectedMove: string

      if (selectedBot.rating <= 2000) {
        // Maia (ELO 300-2000). evaluatePosition transparently uses the server
        // fallback when the local model isn't ready, so a move always comes back.
        if (status !== 'ready' && !engineWaitTracked.current) {
          engineWaitTracked.current = true
          track(ANALYTICS_EVENTS.PLAY_ENGINE_WAIT, {
            engine: 'maia',
            bot: selectedBot.id,
            local_status: status,
          })
        }

        // elo_oppo mirrors elo_self: the model plays most naturally when it
        // believes the matchup is symmetric, especially at low ratings.
        const evaluation = await evaluatePosition(currentFen, selectedBot.rating, selectedBot.rating)

        if (!evaluation || !evaluation.policy) {
          console.error('No evaluation returned')
          setThinking(false)
          return
        }

        // Select move with temperature sampling
        selectedMove = selectMove(evaluation.policy, 1.0)
      } else {
        // Stockfish (ELO 2100-2600). Never waits on Maia; the engine
        // self-initializes if a move is requested before it's ready.
        if (stockfishPlay.status !== 'ready' && !engineWaitTracked.current) {
          engineWaitTracked.current = true
          track(ANALYTICS_EVENTS.PLAY_ENGINE_WAIT, {
            engine: 'stockfish',
            bot: selectedBot.id,
            local_status: stockfishPlay.status,
          })
        }

        const move = await stockfishPlay.getMove(currentFen, selectedBot.rating)
        if (!move) {
          console.error('No move returned from Stockfish')
          setThinking(false)
          return
        }
        selectedMove = move
      }

      // Bailed out of the game while the engine was thinking → drop the move.
      if (generation !== moveGeneration.current) return

      // Apply move
      const from = selectedMove.substring(0, 2) as Key
      const to = selectedMove.substring(2, 4) as Key
      const promotion = selectedMove.length > 4 ? selectedMove[4] : undefined

      chess.move({
        from,
        to,
        promotion: promotion as 'q' | 'r' | 'b' | 'n' | undefined,
      })

      setFen(chess.fen())
      setLastMove([from, to])
      setPlayerCanMove(true)
      checkGameOver()
    } catch (err) {
      console.error('Bot move error:', err)
      if (generation === moveGeneration.current) setPlayerCanMove(true)
    } finally {
      // Don't clobber a fresh game's thinking state if we were invalidated.
      if (generation === moveGeneration.current) setThinking(false)
    }
  }

  const handleMove = (from: Key, to: Key) => {
    // Attempt the move
    try {
      const moves = chess.moves({ verbose: true })
      const move = moves.find((m) => m.from === from && m.to === to)

      if (!move) return false

      // Check for promotion
      if (
        move.piece === 'p' &&
        ((move.to[1] === '8' && chess.turn() === 'w') ||
          (move.to[1] === '1' && chess.turn() === 'b'))
      ) {
        // Auto-promote to queen for simplicity
        chess.move({ from, to, promotion: 'q' })
      } else {
        chess.move({ from, to })
      }

      setFen(chess.fen())
      setLastMove([from, to])
      setPlayerCanMove(false)

      if (chess.isGameOver()) {
        checkGameOver()
        return true
      }

      // Bot's turn after a delay
      scheduleBotMove()
      return true
    } catch (err) {
      console.error('Move error:', err)
      return false
    }
  }

  // `ended` shares `playing`'s history slot (replace, not push) so Back from a
  // finished game returns to `setup` rather than into the dead game.
  const enterEndedPhase = () => {
    setGamePhase('ended')
    if (selectedBot) history.replace({ phase: 'ended', bot: selectedBot.id })
  }

  const checkGameOver = () => {
    if (chess.isCheckmate()) {
      setGameResult(chess.turn() === 'w' ? 'Black wins by checkmate!' : 'White wins by checkmate!')
      setGameOutcome(outcomeFromPosition(chess, actualPlayerColor))
      setResigned(false)
      enterEndedPhase()
    } else if (chess.isDraw()) {
      if (chess.isStalemate()) {
        setGameResult('Draw by stalemate')
      } else if (chess.isThreefoldRepetition()) {
        setGameResult('Draw by threefold repetition')
      } else if (chess.isInsufficientMaterial()) {
        setGameResult('Draw by insufficient material')
      } else {
        setGameResult('Draw by 50-move rule')
      }
      setGameOutcome('draw')
      setResigned(false)
      enterEndedPhase()
    }
  }

  const resetGame = () => {
    cancelBotWork()
    chess.reset()
    setFen(chess.fen())
    setGamePhase('selecting')
    setGameResult(null)
    setGameOutcome(null)
    setResigned(false)
    setModalOpen(false)
    setLastMove(undefined)
    setSelectedBot(null)
    history.push({ phase: 'selecting', bot: null })
  }

  // Player concedes: end the game as a loss for them (bot wins). Mirrors how
  // checkGameOver ends the game so the ended-phase UI is identical.
  const handleResign = () => {
    if (!selectedBot || gamePhase !== 'playing') return
    cancelBotWork()
    setPlayerCanMove(false)
    setGameResult(
      playText(t, 'resigned', `You resigned. ${selectedBot.name} wins!`, {
        name: selectedBot.name,
      }),
    )
    setGameOutcome('botWin')
    setResigned(true)
    enterEndedPhase()
  }

  // Play again / Rematch: fresh game vs the same bot.
  const handlePlayAgain = () => startGame(selectedBot)

  // Try a stronger bot: fresh game vs the next bot in BOTS order.
  const handleTryStronger = (nextBot: Bot) => startGame(nextBot)

  // Visible back arrow shown in setup/playing/ended. Delegates to
  // history.back() so the existing popstate logic runs the phase transition
  // (playing → setup → selecting) and stale bot-move cancellation. Styled from
  // the selected bot's world theme to match the rest of the play screen.
  const backButton = selectedBot && (
    <Box
      component="button"
      type="button"
      onClick={() => history.back()}
      aria-label={playText(t, 'back', 'Back')}
      data-testid="play-back-button"
      sx={{
        position: 'absolute',
        top: { xs: 10, sm: 16 },
        left: { xs: 10, sm: 16 },
        zIndex: 2,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 40,
        height: 40,
        p: 0,
        border: 'none',
        borderRadius: '999px',
        cursor: 'pointer',
        color: gameTheme(selectedBot).deep,
        bgcolor: 'rgba(255,255,255,0.92)',
        boxShadow: `0 4px 12px ${gameTheme(selectedBot).deep}33`,
        transition: 'transform 120ms ease, box-shadow 120ms ease',
        '&:hover': {
          transform: 'translateY(-1px)',
          boxShadow: `0 6px 16px ${gameTheme(selectedBot).deep}47`,
        },
        '&:focus-visible': {
          outline: `3px solid ${gameTheme(selectedBot).main}`,
          outlineOffset: '2px',
        },
      }}
    >
      <Box component="span" aria-hidden="true" sx={{ fontSize: 22, lineHeight: 1 }}>
        ←
      </Box>
    </Box>
  )

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', p: { xs: 1, sm: 3 } }}>
      {(error || stockfishPlay.error) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error || stockfishPlay.error}
        </Alert>
      )}

      {/* Bot selection phase */}
      {gamePhase === 'selecting' && (
        <Box
          sx={{
            bgcolor: '#F3F7FF',
            borderRadius: '24px',
            p: { xs: 2, sm: 3, md: 4 },
          }}
        >
          {/* Two labeled sections: bots (primary) and, when online play is on,
              a friend challenge card beside the grid on desktop so it's visible
              without scrolling past the whole grid. */}
          <Box
            sx={{
              display: 'grid',
              gap: { xs: 4, md: 4 },
              alignItems: 'start',
              gridTemplateColumns: {
                xs: '1fr',
                md: ONLINE_PLAY_ENABLED ? 'minmax(0, 1fr) 340px' : '1fr',
              },
            }}
          >
            {/* Play the bots */}
            <Box component="section" aria-labelledby="play-bots-heading">
              <SectionHeading id="play-bots-heading">
                {playText(t, 'sectionBots', 'Play the bots')}
              </SectionHeading>
              <BotGrid
                selectedBotId={selectedBot?.id || null}
                onSelectBot={handleBotSelect}
              />
            </Box>

            {/* Play a friend — online play (phase 3), gated by ONLINE_PLAY_ENABLED. */}
            {ONLINE_PLAY_ENABLED && (
              <Box component="section" aria-labelledby="play-friend-heading">
                <SectionHeading id="play-friend-heading">
                  {playText(t, 'sectionFriend', 'Play a friend')}
                </SectionHeading>
                <PlayFriendCard />
              </Box>
            )}
          </Box>
        </Box>
      )}

      {/* Game setup phase */}
      {gamePhase === 'setup' && selectedBot && (
        <Box sx={{ position: 'relative', maxWidth: 660, mx: 'auto' }}>
          {backButton}
          <GameSetup
            bot={selectedBot}
            playerColor={playerColor}
            onColorChange={setPlayerColor}
            onPlay={() => startGame()}
            onChangeBot={handleChangeBot}
          />
        </Box>
      )}

      {/* Playing/ended phase — V3 "Immersive World" screen */}
      {(gamePhase === 'playing' || gamePhase === 'ended') && selectedBot && (
        <Box
          data-testid="game-screen"
          sx={{
            position: 'relative',
            overflow: 'hidden',
            borderRadius: '24px',
            p: { xs: 1, sm: 3 },
            // The whole in-game screen is dipped in the tier's world gradient.
            background: gameTheme(selectedBot).screenGradient,
          }}
        >
          {backButton}

          {/* Decorative low-opacity floating scenery emojis */}
          {(() => {
            const [d1, d2, d3] = gameTheme(selectedBot).deco
            const decoSx = {
              position: 'absolute',
              userSelect: 'none',
              opacity: 0.18,
              pointerEvents: 'none',
              zIndex: 0,
            } as const
            return (
              <Box aria-hidden="true">
                <Box component="span" sx={{ ...decoSx, top: 14, right: 18, fontSize: '56px' }}>
                  {d1}
                </Box>
                <Box component="span" sx={{ ...decoSx, top: 200, left: -8, fontSize: '44px' }}>
                  {d2}
                </Box>
                <Box component="span" sx={{ ...decoSx, bottom: 48, right: -6, fontSize: '64px' }}>
                  {d3}
                </Box>
              </Box>
            )
          })()}

          <Box
            sx={{
              position: 'relative',
              zIndex: 1,
              display: 'grid',
              gap: 2,
              alignItems: 'start',
              justifyContent: { md: 'center' },
              // Fixed side column: content changes (thinking bubble, syncing
              // pill) must never resize the column and re-center the board.
              gridTemplateColumns: { xs: '1fr', md: 'auto 320px' },
              gridTemplateAreas: {
                xs: '"header" "board" "dock"',
                md: '"board header" "board dock"',
              },
            }}
          >
            {/* Bot header */}
            <Box sx={{ gridArea: 'header' }}>
              <GameHeader
                bot={selectedBot}
                thinking={thinking}
                syncing={usingServerFallback && status !== 'ready'}
              />
            </Box>

            {/* Board card */}
            <Box
              sx={{
                gridArea: 'board',
                borderRadius: '20px',
                overflow: 'hidden',
                border: 'solid rgba(255,255,255,.95)',
                borderWidth: { xs: '3px', sm: '5px' },
                boxShadow: `0 16px 40px ${gameTheme(selectedBot).deep}59`,
                lineHeight: 0,
              }}
            >
              <ChessgroundBoard
                fen={fen}
                onMove={handleMove}
                orientation={actualPlayerColor === 'w' ? 'white' : 'black'}
                lastMove={lastMove}
                movable={playerCanMove && !thinking}
              />
            </Box>

            {/* Bottom dock */}
            <Box sx={{ gridArea: 'dock' }}>
              <GameDock
                bot={selectedBot}
                playerColor={actualPlayerColor}
                gameResult={gameResult}
                onNewGame={resetGame}
                onResign={handleResign}
              />
            </Box>
          </Box>

          {gameOutcome && (
            <GameEndModal
              bot={selectedBot}
              outcome={gameOutcome}
              resigned={resigned}
              open={modalOpen}
              onClose={() => setModalOpen(false)}
              onPlayAgain={handlePlayAgain}
              onTryStronger={handleTryStronger}
              onChooseAnother={resetGame}
            />
          )}
        </Box>
      )}
    </Box>
  )
}

/** Fredoka section heading for the two /play sections (bots / friend). */
function SectionHeading({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <Box
      component="h2"
      id={id}
      sx={{
        m: 0,
        mb: { xs: 1.5, sm: 2 },
        fontFamily: fredoka.style.fontFamily,
        fontWeight: 700,
        fontSize: { xs: '22px', sm: '26px' },
        color: '#1E2A44',
      }}
    >
      {children}
    </Box>
  )
}
