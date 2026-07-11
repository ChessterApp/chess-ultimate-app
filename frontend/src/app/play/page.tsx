'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Chess } from 'chess.js'
import { Box, Alert } from '@mui/material'
import { useTranslations } from 'next-intl'
import ChessgroundBoard from '@/components/chess/ChessgroundBoard'
import BotGrid from '@/components/play/BotGrid'
import GameSetup from '@/components/play/GameSetup'
import GameHeader from '@/components/play/GameHeader'
import GameDock from '@/components/play/GameDock'
import { useMaia } from '@/hooks/useMaia'
import { useStockfishPlay } from '@/hooks/useStockfishPlay'
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events'
import { playText } from '@/lib/botI18n'
import type { Bot } from '@/data/bots'
import { gameTheme } from '@/data/bots'
import type { Key } from 'chessground/types'

// Import chessground CSS
import 'chessground/assets/chessground.base.css'
import 'chessground/assets/chessground.brown.css'
import '@/styles/chessground-theme.css'

type GamePhase = 'selecting' | 'setup' | 'playing' | 'ended'
type PlayerColor = 'white' | 'black' | 'random'

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
  const [thinking, setThinking] = useState(false)
  const [lastMove, setLastMove] = useState<[Key, Key] | undefined>(undefined)
  const [playerCanMove, setPlayerCanMove] = useState(true)

  // Auto-download model when not cached
  const downloadTriggered = useRef(false)

  useEffect(() => {
    if (status === 'no-cache' && !downloadTriggered.current) {
      downloadTriggered.current = true
      downloadModel().catch((err) => console.error('Auto-download failed:', err))
    }
  }, [status, downloadModel])

  const handleBotSelect = (bot: Bot) => {
    setSelectedBot(bot)
    setGamePhase('setup')
  }

  const handleChangeBot = () => {
    setGamePhase('selecting')
  }

  const startGame = () => {
    if (!selectedBot) return

    // Determine actual player color
    let actualColor: 'w' | 'b' = 'w'
    if (playerColor === 'random') {
      actualColor = Math.random() < 0.5 ? 'w' : 'b'
    } else {
      actualColor = playerColor === 'white' ? 'w' : 'b'
    }

    setActualPlayerColor(actualColor)
    chess.reset()
    setFen(chess.fen())
    setGameResult(null)
    setGamePhase('playing')
    setLastMove(undefined)
    engineWaitTracked.current = false

    // If player is black, bot moves first
    if (actualColor === 'b') {
      setPlayerCanMove(false)
      setTimeout(() => makeBotMove(), 500)
    } else {
      setPlayerCanMove(true)
    }
  }

  const makeBotMove = async () => {
    if (chess.isGameOver() || !selectedBot) {
      checkGameOver()
      return
    }

    setThinking(true)
    try {
      const currentFen = chess.fen()
      let selectedMove: string

      if (selectedBot.rating <= 2000) {
        // Maia (ELO 1100-2000). evaluatePosition transparently uses the server
        // fallback when the local model isn't ready, so a move always comes back.
        if (status !== 'ready' && !engineWaitTracked.current) {
          engineWaitTracked.current = true
          track(ANALYTICS_EVENTS.PLAY_ENGINE_WAIT, {
            engine: 'maia',
            bot: selectedBot.id,
            local_status: status,
          })
        }

        const evaluation = await evaluatePosition(currentFen, selectedBot.rating, 1500)

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
      setPlayerCanMove(true)
    } finally {
      setThinking(false)
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
      setTimeout(() => makeBotMove(), 500)
      return true
    } catch (err) {
      console.error('Move error:', err)
      return false
    }
  }

  const checkGameOver = () => {
    if (chess.isCheckmate()) {
      setGameResult(chess.turn() === 'w' ? 'Black wins by checkmate!' : 'White wins by checkmate!')
      setGamePhase('ended')
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
      setGamePhase('ended')
    }
  }

  const resetGame = () => {
    chess.reset()
    setFen(chess.fen())
    setGamePhase('selecting')
    setGameResult(null)
    setLastMove(undefined)
    setSelectedBot(null)
  }

  // Player concedes: end the game as a loss for them (bot wins). Mirrors how
  // checkGameOver ends the game so the ended-phase UI is identical.
  const handleResign = () => {
    if (!selectedBot || gamePhase !== 'playing') return
    setThinking(false)
    setPlayerCanMove(false)
    setGameResult(
      playText(t, 'resigned', `You resigned. ${selectedBot.name} wins!`, {
        name: selectedBot.name,
      }),
    )
    setGamePhase('ended')
  }

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
          <BotGrid
            selectedBotId={selectedBot?.id || null}
            onSelectBot={handleBotSelect}
          />
        </Box>
      )}

      {/* Game setup phase */}
      {gamePhase === 'setup' && selectedBot && (
        <GameSetup
          bot={selectedBot}
          playerColor={playerColor}
          onColorChange={setPlayerColor}
          onPlay={startGame}
          onChangeBot={handleChangeBot}
        />
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
        </Box>
      )}
    </Box>
  )
}
