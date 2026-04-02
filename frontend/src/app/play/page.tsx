'use client'

import React, { useState, useEffect, useRef } from 'react'
import { Chess } from 'chess.js'
import {
  Box,
  Button,
  Typography,
  Slider,
  FormControl,
  FormLabel,
  RadioGroup,
  FormControlLabel,
  Radio,
  Paper,
  LinearProgress,
  Alert,
} from '@mui/material'
import ChessgroundBoard from '@/components/chess/ChessgroundBoard'
import { useMaia } from '@/hooks/useMaia'
import type { Key } from 'chessground/types'

// Import chessground CSS
import 'chessground/assets/chessground.base.css'
import 'chessground/assets/chessground.brown.css'
import '@/styles/chessground-theme.css'

type GamePhase = 'setup' | 'playing' | 'ended'
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

  // Setup state
  const [maiaRating, setMaiaRating] = useState(1500)
  const [playerColor, setPlayerColor] = useState<PlayerColor>('white')
  const [gamePhase, setGamePhase] = useState<GamePhase>('setup')

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

  const startGame = () => {
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

    // If player is black, Maia moves first
    if (actualColor === 'b') {
      setPlayerCanMove(false)
      setTimeout(() => makeMaiaMove(), 500)
    } else {
      setPlayerCanMove(true)
    }
  }

  const makeMaiaMove = async () => {
    if (chess.isGameOver()) {
      checkGameOver()
      return
    }

    setThinking(true)
    try {
      const currentFen = chess.fen()
      const evaluation = await evaluatePosition(currentFen, maiaRating, 1500)

      if (!evaluation || !evaluation.policy) {
        console.error('No evaluation returned')
        setThinking(false)
        return
      }

      // Select move with temperature sampling
      const selectedMove = selectMove(evaluation.policy, 1.0)

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
      console.error('Maia move error:', err)
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

      // Maia's turn after a delay
      setTimeout(() => makeMaiaMove(), 500)
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
    setGamePhase('setup')
    setGameResult(null)
    setLastMove(undefined)
  }

  return (
    <Box sx={{ maxWidth: 1200, mx: 'auto', p: 3 }}>
      <Typography variant="h4" gutterBottom>
        Play vs Maia Bot
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Inline loading indicator */}
      {(status === 'no-cache' || status === 'downloading' || status === 'loading') && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="subtitle1" gutterBottom>
            {status === 'loading' ? 'Initializing Maia engine...' : 'Loading Maia engine...'}
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

      {gamePhase === 'setup' && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Typography variant="h6" gutterBottom>
            Game Settings
          </Typography>

          <FormControl fullWidth sx={{ mb: 3 }}>
            <FormLabel>Maia Rating: {maiaRating}</FormLabel>
            <Slider
              value={maiaRating}
              onChange={(_, value) => setMaiaRating(value as number)}
              min={1100}
              max={2000}
              step={100}
              marks
              valueLabelDisplay="auto"
            />
            <Typography variant="caption" color="text.secondary">
              Higher rating = stronger play
            </Typography>
          </FormControl>

          <FormControl component="fieldset">
            <FormLabel>Play as</FormLabel>
            <RadioGroup
              value={playerColor}
              onChange={(e) => setPlayerColor(e.target.value as PlayerColor)}
            >
              <FormControlLabel value="white" control={<Radio />} label="White" />
              <FormControlLabel value="black" control={<Radio />} label="Black" />
              <FormControlLabel value="random" control={<Radio />} label="Random" />
            </RadioGroup>
          </FormControl>

          <Button
            variant="contained"
            size="large"
            onClick={startGame}
            disabled={status !== 'ready'}
            sx={{ mt: 3 }}
          >
            {status === 'ready' ? 'Start Game' : 'Loading...'}
          </Button>
        </Paper>
      )}

      {(gamePhase === 'playing' || gamePhase === 'ended') && (
        <Box>
          <Box sx={{ display: 'flex', gap: 3, flexDirection: { xs: 'column', md: 'row' } }}>
            {/* Board */}
            <Box sx={{ flex: 1 }}>
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
                  Maia Rating: {maiaRating}
                </Typography>
                {thinking && (
                  <Typography variant="body2" color="primary" sx={{ mt: 1 }}>
                    Maia is thinking...
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
