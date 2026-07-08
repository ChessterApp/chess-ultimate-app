import Maia, { MaiaStatus } from '@/lib/maia/maia'

// int8-quantized build (~24MB, ~45% smaller than the fp32 download) — see
// scripts/quantize_maia.py. The server fallback keeps using the fp32 model.
const MODEL_URL = '/maia3/maia3_simplified_int8.onnx'
const MODEL_VERSION = '3.1.0-int8'

/** Shut Maia down this long after the last /play consumer unmounts. */
const IDLE_TIMEOUT_MS = 10 * 60 * 1000

export interface MaiaState {
  status: MaiaStatus
  progress: number
  error: string | null
}

type Listener = (state: MaiaState) => void

const INITIAL_STATE: MaiaState = { status: 'loading', progress: 0, error: null }

let instance: Maia | null = null
let state: MaiaState = INITIAL_STATE
const listeners = new Set<Listener>()
let subscriberCount = 0
let idleTimer: ReturnType<typeof setTimeout> | null = null

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
    shutdownMaia()
  }, IDLE_TIMEOUT_MS)
}

function setState(patch: Partial<MaiaState>) {
  state = { ...state, ...patch }
  for (const listener of listeners) {
    listener(state)
  }
}

/** Returns the current cached Maia state (safe during SSR). */
export function getMaiaState(): MaiaState {
  return state
}

/**
 * Returns a cached Maia instance, creating (and starting to load) the ONNX
 * model at most once per browser session. Returns null during SSR or when Web
 * Workers are unavailable.
 */
export function getMaiaInstance(): Maia | null {
  clearIdleTimer()

  if (typeof window === 'undefined' || typeof Worker === 'undefined') {
    return null
  }

  if (!instance) {
    instance = new Maia({
      model: MODEL_URL,
      modelVersion: MODEL_VERSION,
      setStatus: (status) => setState({ status }),
      setProgress: (progress) => setState({ progress }),
      setError: (error) => setState({ error }),
    })
  }

  return instance
}

/**
 * Subscribes to Maia state changes. Registering interest cancels any pending
 * idle shutdown; the returned unsubscribe schedules an idle shutdown once the
 * last subscriber leaves.
 */
export function subscribeMaia(listener: Listener): () => void {
  listeners.add(listener)
  subscriberCount++
  clearIdleTimer()

  let active = true
  return () => {
    if (!active) return
    active = false
    listeners.delete(listener)
    subscriberCount--
    if (subscriberCount <= 0) {
      scheduleIdleShutdown()
    }
  }
}

/** Warms Maia on intent (e.g. hovering the Play nav link). */
export function warmMaia(): void {
  getMaiaInstance()
}

/** Terminates the Maia worker and resets cached state so it re-inits on demand. */
export function shutdownMaia(): void {
  clearIdleTimer()
  if (instance) {
    instance.destroy()
    instance = null
  }
  state = INITIAL_STATE
}

/** Test-only: resets all module state without touching a real worker. */
export function __resetMaiaForTests(): void {
  clearIdleTimer()
  instance = null
  state = INITIAL_STATE
  listeners.clear()
  subscriberCount = 0
}
