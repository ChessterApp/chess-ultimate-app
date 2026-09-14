// Wheel spin physics — a pure, deterministic, DOM-free state machine that
// reproduces the wheelofnames.com "feel": a short linear acceleration into a
// long exponential creep-to-stop. Ported to a fixed-timestep model so it runs
// identically regardless of the display's refresh rate (the rAF driver in
// useWheelPhysics.ts steps it at a fixed 60 ticks/sec via an accumulator).
//
// Angle convention matches geometry.ts: radians, measured CLOCKWISE from the
// top (12 o'clock, where the pointer sits). A larger angle == more clockwise
// rotation, which is what CSS `rotate()` does for positive values.
//
// Winner-first landing: the crypto-uniform selection in random.ts stays
// authoritative. For a given peak speed and decel duration the total rotation
// during deceleration is a deterministic constant D. At the accel->decel
// boundary the (blurred, unobservable) angle is discarded and reset to
// `targetFinalAngle - D`, so that after the fully-deterministic decel the wheel
// lands exactly on the pre-chosen winner angle.

export type WheelPhase = 'idle' | 'accelerating' | 'decelerating' | 'stopped';

export const TWO_PI = Math.PI * 2;

/** Logical simulation rate. The rAF driver steps exactly this many ticks/sec. */
export const TICKS_PER_SECOND = 60;

/** Peak angular speed of a normal spin: ~5.9 rev/sec == ~0.618 rad/tick. */
export const PEAK_SPEED = 0.618;

/**
 * Peak angular speed under reduced motion: ~4 rev/sec (no motion blur). Reduced
 * motion trims the *decorative* extras (idle drift, motion blur) but keeps a
 * real spin — the wheel's whole purpose is the spin, so gutting it to half a
 * turn (the old 0.5 rev/s) defeats the feature and reads as "barely rotates".
 */
export const GENTLE_PEAK_SPEED = (TWO_PI * 4) / TICKS_PER_SECOND;

/** Speed (rad/tick) the decay targets at the final decel tick, before snapping. */
export const END_SPEED = 0.00015;

/** Gentle continuous drift (rad/tick) while idle, before the first spin. */
export const IDLE_SPEED = 0.02;

/** Default total spin wall-clock duration, in seconds. */
export const DEFAULT_SPIN_TIME = 10;

/** Deceleration duration under reduced motion, in seconds (~5.5 rev over 8s). */
export const GENTLE_DECEL_SECONDS = 7;

/** The accelerate phase is capped at 1s (or spinTime/3 for very short spins). */
export const MAX_ACCEL_SECONDS = 1;

export interface TickResult {
  phase: WheelPhase;
  /** Transform angle in radians. */
  angle: number;
  /** Angular speed in rad/tick. */
  speed: number;
  /** Slice-boundary crossings past the pointer during this tick (>= 0). */
  crossings: number;
  /** True only on the single tick that enters the Stopped phase. */
  justStopped: boolean;
}

export interface SpinParams {
  /** Total spin wall-clock, seconds (accel + decel). Default {@link DEFAULT_SPIN_TIME}. */
  spinTime?: number;
  /** Absolute final angle (radians). Its value mod 2π must center the winner. */
  targetFinalAngle: number;
  /** Segment count — sets the slice width used for boundary-crossing events. */
  segments: number;
  /** Angle the accel phase starts from (radians). Default 0. */
  startAngle?: number;
  /** Reduced-motion mode: low peak + short decel, still lands exactly. */
  gentle?: boolean;
}

/** Accelerate-phase duration in seconds for a given total spin time. */
export function accelDurationSeconds(spinTime: number): number {
  return Math.min(MAX_ACCEL_SECONDS, spinTime / 3);
}

/** Decelerate-phase duration in seconds. Gentle mode uses a fixed short decel. */
export function decelDurationSeconds(spinTime: number, gentle: boolean): number {
  if (gentle) return GENTLE_DECEL_SECONDS;
  return Math.max(0, spinTime - accelDurationSeconds(spinTime));
}

/**
 * Per-tick multiplicative decay so that after `decelTicks` ticks the speed falls
 * from `peak` to `endSpeed`: peak * decay^decelTicks == endSpeed.
 */
export function decayFactor(peak: number, decelTicks: number, endSpeed = END_SPEED): number {
  if (decelTicks <= 0) return 0;
  return Math.pow(endSpeed / peak, 1 / decelTicks);
}

/**
 * Closed-form total rotation during the accelerate phase. Speed ramps linearly
 * 0 -> peak over `accelTicks` ticks (tick i has speed peak*i/accelTicks), so the
 * sum is peak * (accelTicks + 1) / 2.
 */
export function accelRotation(peak: number, accelTicks: number): number {
  if (accelTicks <= 0) return 0;
  return (peak * (accelTicks + 1)) / 2;
}

/**
 * Closed-form total rotation during the decelerate phase: the geometric series
 * sum_{j=1..decelTicks} peak * decay^j (speed is decayed BEFORE it is applied on
 * each tick, matching the tick() integration order).
 */
export function decelRotation(peak: number, decay: number, decelTicks: number): number {
  if (decelTicks <= 0) return 0;
  if (decay === 1) return peak * decelTicks;
  return (peak * decay * (1 - Math.pow(decay, decelTicks))) / (1 - decay);
}

/**
 * Final angle (radians, mod 2π) that places segment `index` (of `count`) under
 * the top pointer. `jitter` is a fraction of the slice width in (-0.5, 0.5) that
 * offsets the landing from dead-center; it is clamped to stay inside the slice.
 */
export function winnerAngleRad(index: number, count: number, jitter = 0): number {
  const slice = TWO_PI / count;
  const j = Math.max(-0.49, Math.min(0.49, jitter));
  const local = index * slice + slice / 2 + j * slice;
  return ((TWO_PI - local) % TWO_PI + TWO_PI) % TWO_PI;
}

/**
 * Fixed-timestep wheel spin. Construct via {@link WheelPhysics.spin} for a real
 * spin or {@link WheelPhysics.idle} for the pre-spin drift, then call
 * {@link WheelPhysics.tick} once per fixed timestep.
 */
export class WheelPhysics {
  private _phase: WheelPhase;
  private _angle: number;
  private _speed: number;

  private readonly slice: number;

  // Spin-only precomputed constants (unused in idle mode).
  private readonly peak: number;
  private readonly accelTicks: number;
  private readonly decelTicks: number;
  private readonly accelPerTick: number;
  private readonly decay: number;
  private readonly D: number;
  private readonly decelStartAngle: number;
  private readonly targetFinalAngle: number;

  // Mutable per-tick state.
  private phaseTick = 0; // ticks elapsed within the current phase
  private jumpPending = false; // discard-and-reset scheduled for the first decel tick
  // Accumulated REAL motion (excludes the invisible accel->decel jump) used to
  // count boundary crossings past the pointer.
  private crossAccum = 0;
  private crossFloor = 0;

  private constructor(phase: WheelPhase, params: SpinParams) {
    this._phase = phase;
    this._angle = params.startAngle ?? 0;
    this._speed = 0;
    this.slice = TWO_PI / params.segments;

    const gentle = !!params.gentle;
    const spinTime = params.spinTime ?? DEFAULT_SPIN_TIME;
    this.peak = gentle ? GENTLE_PEAK_SPEED : PEAK_SPEED;
    this.accelTicks = Math.max(1, Math.round(accelDurationSeconds(spinTime) * TICKS_PER_SECOND));
    this.decelTicks = Math.max(1, Math.round(decelDurationSeconds(spinTime, gentle) * TICKS_PER_SECOND));
    this.accelPerTick = this.peak / this.accelTicks;
    this.decay = decayFactor(this.peak, this.decelTicks);
    this.D = decelRotation(this.peak, this.decay, this.decelTicks);
    this.targetFinalAngle = params.targetFinalAngle;
    this.decelStartAngle = params.targetFinalAngle - this.D;
  }

  /** A real spin: accelerate, discard-and-reset, decelerate onto the winner. */
  static spin(params: SpinParams): WheelPhysics {
    return new WheelPhysics('accelerating', params);
  }

  /** Idle drift used before the first spin (and after a reset). */
  static idle(segments: number, startAngle = 0): WheelPhysics {
    return new WheelPhysics('idle', { segments, startAngle, targetFinalAngle: 0 });
  }

  /**
   * Absolute final angle that lands `targetMod` (mod 2π) under the pointer while
   * keeping the accel->decel reset jump minimal (< one turn). The decel phase
   * begins essentially where the accel phase ended, so the spin reads as one
   * continuous arc instead of the multi-turn teleport a fixed turn-count caused.
   */
  static resolveTarget(opts: {
    startAngle: number;
    targetMod: number;
    gentle?: boolean;
    spinTime?: number;
  }): number {
    const gentle = !!opts.gentle;
    const spinTime = opts.spinTime ?? DEFAULT_SPIN_TIME;
    const peak = gentle ? GENTLE_PEAK_SPEED : PEAK_SPEED;
    const accelTicks = Math.max(1, Math.round(accelDurationSeconds(spinTime) * TICKS_PER_SECOND));
    const decelTicks = Math.max(1, Math.round(decelDurationSeconds(spinTime, gentle) * TICKS_PER_SECOND));
    const decay = decayFactor(peak, decelTicks);
    const D = decelRotation(peak, decay, decelTicks);
    // Angle the wheel would reach with a zero-length reset jump.
    const base = opts.startAngle + accelRotation(peak, accelTicks) + D;
    const baseMod = ((base % TWO_PI) + TWO_PI) % TWO_PI;
    const targetMod = ((opts.targetMod % TWO_PI) + TWO_PI) % TWO_PI;
    const forwardAdjust = (((targetMod - baseMod) % TWO_PI) + TWO_PI) % TWO_PI;
    return base + forwardAdjust; // decelStart == accelEnd + forwardAdjust (< 2π)
  }

  get phase(): WheelPhase {
    return this._phase;
  }
  get angle(): number {
    return this._angle;
  }
  get speed(): number {
    return this._speed;
  }
  /** Peak angular speed (rad/tick) this spin ramps up to. */
  get peakSpeed(): number {
    return this.peak;
  }
  /** Deterministic total rotation (radians) during the decelerate phase. */
  get decelRotationConstant(): number {
    return this.D;
  }
  get accelTickCount(): number {
    return this.accelTicks;
  }
  get decelTickCount(): number {
    return this.decelTicks;
  }
  get decayPerTick(): number {
    return this.decay;
  }

  private countCrossings(): number {
    const f = Math.floor(this.crossAccum / this.slice);
    const c = f - this.crossFloor;
    this.crossFloor = f;
    return c;
  }

  private result(phase: WheelPhase, crossings: number, justStopped: boolean): TickResult {
    return {
      phase,
      angle: this._angle,
      speed: this._speed,
      crossings,
      justStopped,
    };
  }

  /** Advance the simulation by one fixed timestep. */
  tick(): TickResult {
    switch (this._phase) {
      case 'idle': {
        this._speed = IDLE_SPEED;
        this._angle += this._speed;
        this.crossAccum += this._speed;
        return this.result('idle', this.countCrossings(), false);
      }

      case 'accelerating': {
        this.phaseTick += 1;
        this._speed = this.accelPerTick * this.phaseTick;
        this._angle += this._speed;
        this.crossAccum += this._speed;
        const crossings = this.countCrossings();
        if (this.phaseTick >= this.accelTicks) {
          // Enter decel next tick. Speed carries over as the peak (v0); the
          // angle is discarded then (see jumpPending) — invisible under blur.
          this._phase = 'decelerating';
          this._speed = this.peak;
          this.phaseTick = 0;
          this.jumpPending = true;
        }
        // This tick moved at accel speed — report it as accelerating even if the
        // internal phase has already flipped for the next tick.
        return this.result('accelerating', crossings, false);
      }

      case 'decelerating': {
        if (this.jumpPending) {
          // Discard the accumulated angle and reset so the deterministic decel
          // lands exactly on targetFinalAngle. Not added to crossAccum: this
          // jump produces no real (audible) boundary crossings.
          this._angle = this.decelStartAngle;
          this.jumpPending = false;
        }
        this.phaseTick += 1;
        this._speed *= this.decay;
        this._angle += this._speed;
        this.crossAccum += this._speed;
        const crossings = this.countCrossings();
        if (this.phaseTick >= this.decelTicks) {
          this._phase = 'stopped';
          this._speed = 0;
          // Snap away the ~1e-10 residual so the landing is exact.
          this._angle = this.targetFinalAngle;
          return this.result('stopped', crossings, true);
        }
        return this.result('decelerating', crossings, false);
      }

      case 'stopped':
      default:
        return this.result('stopped', 0, false);
    }
  }
}
