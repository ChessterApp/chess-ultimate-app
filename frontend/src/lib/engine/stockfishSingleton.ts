import { UciEngine } from '@/stockfish/engine/UciEngine'
import { Stockfish17Point } from '@/stockfish/engine/Stockfish17Point'
import { Stockfish16 } from '@/stockfish/engine/Stockfish16'
import { Stockfish11 } from '@/stockfish/engine/Stockfish11'

/** Shut the engine down this long after the last /play consumer unmounts. */
const IDLE_TIMEOUT_MS = 10 * 60 * 1000
const INITIAL_ELO = 2100

let enginePromise: Promise<UciEngine> | null = null
let engineInstance: UciEngine | null = null
let currentElo = INITIAL_ELO
let subscriberCount = 0
let idleTimer: ReturnType<typeof setTimeout> | null = null

/**
 * Attempts to initialize engines in order: SF17.1 → SF16 → SF11.
 * Returns the first engine that initializes successfully, or throws if all fail.
 */
async function initWithFallback(): Promise<UciEngine> {
  // Try SF17.1 first (best quality)
  if (Stockfish17Point.isSupported()) {
    try {
      const engine = new Stockfish17Point()
      await engine.init()
      if (!engine.crashed) return engine
      engine.shutdown()
    } catch (err) {
      console.warn('SF17.1 init failed, trying SF16:', err)
    }
  }

  // Try SF16 (good quality, smaller)
  if (Stockfish16.isSupported()) {
    try {
      const engine = new Stockfish16()
      await engine.init()
      if (!engine.crashed) return engine
      engine.shutdown()
    } catch (err) {
      console.warn('SF16 init failed, trying SF11:', err)
    }
  }

  // Fall back to SF11 (always works, no SIMD)
  const engine = new Stockfish11()
  await engine.init()
  return engine
}

function clearIdleTimer() {
  if (idleTimer) {
    clearTimeout(idleTimer)
    idleTimer = null
  }
}

function scheduleIdleShutdown() {
  clearIdleTimer()
  idleTimer = setTimeout(() => {
    idleTimer = null
    shutdownStockfish()
  }, IDLE_TIMEOUT_MS)
}

/**
 * Returns a cached promise resolving to a ready Stockfish engine with
 * UCI_LimitStrength enabled. Initialization runs at most once per browser
 * session; subsequent calls reuse the in-flight or resolved engine.
 */
export function getStockfishEngine(): Promise<UciEngine> {
  clearIdleTimer()

  if (!enginePromise) {
    enginePromise = (async () => {
      const engine = await initWithFallback()

      await engine.sendUciCommands(
        [
          'setoption name UCI_LimitStrength value true',
          `setoption name UCI_Elo value ${INITIAL_ELO}`,
          'isready',
        ],
        'readyok',
      )

      engineInstance = engine
      currentElo = INITIAL_ELO
      return engine
    })()

    // Allow a retry on the next call if initialization failed.
    enginePromise.catch(() => {
      enginePromise = null
    })
  }

  return enginePromise
}

/**
 * Registers interest in the engine (e.g. a mounted /play consumer), cancelling
 * any pending idle shutdown. Returns an unsubscribe function that schedules an
 * idle shutdown once the last subscriber leaves.
 */
export function subscribeStockfish(): () => void {
  subscriberCount++
  clearIdleTimer()

  let active = true
  return () => {
    if (!active) return
    active = false
    subscriberCount--
    if (subscriberCount <= 0) {
      scheduleIdleShutdown()
    }
  }
}

/**
 * Gets the best move for the given FEN at the target ELO, updating the engine's
 * UCI_Elo only when it changes. ELO state is tracked on the singleton so it
 * stays correct across remounts.
 */
export async function getStockfishMove(
  fen: string,
  targetElo: number,
): Promise<string | null> {
  const engine = engineInstance ?? (await getStockfishEngine())

  if (targetElo !== currentElo) {
    await engine.sendUciCommands(
      [`setoption name UCI_Elo value ${targetElo}`, 'isready'],
      'readyok',
    )
    currentElo = targetElo
  }

  const messages = await engine.sendUciCommands(
    [`position fen ${fen}`, 'go depth 12'],
    'bestmove',
  )

  const bestmoveLine = messages.find((msg) => msg.startsWith('bestmove'))
  if (!bestmoveLine) {
    console.error('No bestmove found in response')
    return null
  }

  // Extract move from "bestmove e2e4" or "bestmove e2e4 ponder d7d5"
  const parts = bestmoveLine.split(' ')
  if (parts.length < 2) {
    console.error('Invalid bestmove format:', bestmoveLine)
    return null
  }

  return parts[1]
}

/** Kicks off engine initialization without registering a subscriber. */
export function warmStockfish(): void {
  getStockfishEngine().catch(() => {})
}

/** Shuts down the engine and clears cached state so it re-inits on demand. */
export function shutdownStockfish(): void {
  clearIdleTimer()
  if (engineInstance) {
    engineInstance.shutdown()
    engineInstance = null
  }
  enginePromise = null
  currentElo = INITIAL_ELO
}

/** Test-only: resets all module state without touching a real worker. */
export function __resetStockfishForTests(): void {
  clearIdleTimer()
  engineInstance = null
  enginePromise = null
  currentElo = INITIAL_ELO
  subscriberCount = 0
}
