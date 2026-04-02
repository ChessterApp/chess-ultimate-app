'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Chess } from 'chess.js'
import {
  Box,
  Button,
  Typography,
  Paper,
  LinearProgress,
  Alert,
} from '@mui/material'
import ChessgroundBoard from '@/components/chess/ChessgroundBoard'
import BotGrid from '@/components/play/BotGrid'
import GameSetup from '@/components/play/GameSetup'
import { useMaia } from '@/hooks/useMaia'
import { useStockfishPlay } from '@/hooks/useStockfishPlay'
import type { Bot } from '@/data/bots'
import { getBotById } from '@/data/bots'
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
  const { status, progress, error, evaluatePosition, downloadModel } = useMaia()
  const stockfishPlay = useStockfishPlay()

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
        // Use Maia for ELO 1100-2000
        const evaluation = await evaluatePosition(currentFen, selectedBot.rating, 1500)

        if (!evaluation || !evaluation.policy) {
          console.error('No evaluation returned')
          setThinking(false)
          return
        }

        // Select move with temperature sampling
        selectedMove = selectMove(evaluation.policy, 1.0)
      } else {
        // Use Stockfish for ELO 2100-2600
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

  // Check if engines are ready for selected bot
  const isEngineReady = selectedBot
    ? selectedBot.rating <= 2000
      ? status === 'ready'
      : stockfishPlay.status === 'ready'
    : false

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Play vs Bot
      </Typography>

      {/* Inline loading indicator */}
      {(status === 'no-cache' || status === 'downloading' || status === 'loading' || stockfishPlay.status === 'loading') && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="subtitle1" gutterBottom>
            {status === 'loading' || stockfishPlay.status === 'loading'
              ? 'Initializing engine...'
              : 'Downloading engine...'}
          </Typography>
          <LinearProgress
            variant={status === 'downloading' ? 'determinate' : 'indeterminate'}
            value={status === 'downloading' ? progress : undefined}
          />
          {status === 'downloading' && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
              {progress.toFixed(0)}% — one-time download, cached for future visits
            </Typography>
          )}
        </Paper>
      )}

      {(error || stockfishPlay.error) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error || stockfishPlay.error}
        </Alert>
      )}

      {/* Bot selection phase */}
      {gamePhase === 'selecting' && (
        <BotGrid
          selectedBotId={selectedBot?.id || null}
          onSelectBot={handleBotSelect}
        />
      )}

      {/* Game setup phase */}
      {gamePhase === 'setup' && selectedBot && (
        <GameSetup
          bot={selectedBot}
          playerColor={playerColor}
          onColorChange={setPlayerColor}
          onPlay={startGame}
          onChangeBot={handleChangeBot}
          disabled={!isEngineReady}
        />
      )}

      {/* Playing/ended phase */}
      {(gamePhase === 'playing' || gamePhase === 'ended') && selectedBot && (
        <Box>
          <Box sx={{ display: 'flex', gap: 3, flexDirection: { xs: 'column', md: 'row' } }}>
            {/* Board */}
            <Box sx={{ flexShrink: 0 }}>
              <ChessgroundBoard
                fen={fen}
                onMove={handleMove}
                orientation={actualPlayerColor === 'w' ? 'white' : 'black'}
                lastMove={lastMove}
                movable={playerCanMove && !thinking}
              />
            </Box>

            {/* Info Panel */}
            <Box sx={{ width: { xs: '100%', md: 300 } }}>
              <Paper sx={{ p: 2, mb: 2 }}>
                <Typography variant="subtitle2" gutterBottom>
                  Game Info
                </Typography>
                <Typography variant="body2">
                  You: {actualPlayerColor === 'w' ? 'White' : 'Black'}
                </Typography>
                <Typography variant="body2">
                  {selectedBot.name} ({selectedBot.rating})
                </Typography>
                {thinking && (
                  <Typography variant="body2" color="primary" sx={{ mt: 1 }}>
                    {selectedBot.name} is thinking...
                  </Typography>
                )}
              </Paper>

              {gameResult && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  {gameResult}
                </Alert>
              )}

              <Button
                variant="outlined"
                fullWidth
                onClick={resetGame}
                sx={{ mb: 1 }}
              >
                New Game
              </Button>
            </Box>
          </Box>
        </Box>
      )}
    </Box>
  )
}
