import { describe, it, expect } from 'vitest';
import {
  WheelPhysics,
  winnerAngleRad,
  accelRotation,
  decelRotation,
  decayFactor,
  accelDurationSeconds,
  decelDurationSeconds,
  PEAK_SPEED,
  GENTLE_PEAK_SPEED,
  END_SPEED,
  IDLE_SPEED,
  TWO_PI,
  TICKS_PER_SECOND,
  DEFAULT_SPIN_TIME,
} from '../physics';
import { pointerSegmentIndex } from '../geometry';

const RAD_TO_DEG = 180 / Math.PI;

/** Run a spin to completion, returning every tick result plus aggregates. */
function runToStop(phys: WheelPhysics, maxTicks = 100_000) {
  const results = [];
  let totalCrossings = 0;
  let stoppedAt = -1;
  for (let i = 0; i < maxTicks; i++) {
    const r = phys.tick();
    results.push(r);
    totalCrossings += r.crossings;
    if (r.justStopped) {
      stoppedAt = i + 1; // ticks elapsed (1-indexed)
      break;
    }
  }
  return { results, totalCrossings, stoppedAt };
}

describe('duration helpers', () => {
  it('caps the accel phase at 1s (or spinTime/3 for short spins)', () => {
    expect(accelDurationSeconds(10)).toBe(1);
    expect(accelDurationSeconds(2)).toBeCloseTo(2 / 3);
  });
  it('gives the remaining time to decel in normal mode', () => {
    expect(decelDurationSeconds(10, false)).toBe(9);
  });
  it('uses a fixed 7s decel in gentle mode', () => {
    expect(decelDurationSeconds(10, true)).toBe(7);
  });
});

describe('closed-form rotation helpers', () => {
  it('decayFactor brings peak down to END_SPEED over decelTicks', () => {
    const decay = decayFactor(PEAK_SPEED, 540);
    expect(PEAK_SPEED * decay ** 540).toBeCloseTo(END_SPEED, 9);
  });
  it('accelRotation is the linear ramp sum', () => {
    // peak*(n+1)/2
    expect(accelRotation(0.6, 60)).toBeCloseTo((0.6 * 61) / 2, 9);
  });
});

describe('WheelPhysics accelerate phase', () => {
  it('ramps linearly to the peak speed at the final accel tick', () => {
    const phys = WheelPhysics.spin({ targetFinalAngle: 100, segments: 6 });
    const accelTicks = phys.accelTickCount;
    expect(accelTicks).toBe(TICKS_PER_SECOND); // 1s at 60tps for a 10s spin
    let last;
    for (let i = 0; i < accelTicks; i++) last = phys.tick();
    expect(last!.phase).toBe('accelerating');
    expect(last!.speed).toBeCloseTo(PEAK_SPEED, 9);
    // Halfway through, speed is about half the peak (linear ramp).
    const half = WheelPhysics.spin({ targetFinalAngle: 100, segments: 6 });
    let mid;
    for (let i = 0; i < accelTicks / 2; i++) mid = half.tick();
    expect(mid!.speed).toBeCloseTo(PEAK_SPEED / 2, 2);
  });

  it('transitions accelerating -> decelerating on the next tick after peak', () => {
    const phys = WheelPhysics.spin({ targetFinalAngle: 100, segments: 6 });
    for (let i = 0; i < phys.accelTickCount; i++) phys.tick();
    const first = phys.tick();
    expect(first.phase).toBe('decelerating');
  });
});

describe('WheelPhysics total duration', () => {
  it('runs for exactly spinTime worth of ticks', () => {
    const phys = WheelPhysics.spin({ targetFinalAngle: 100, segments: 8, spinTime: DEFAULT_SPIN_TIME });
    const { stoppedAt } = runToStop(phys);
    // accel(60) + decel(540) = 600 ticks == 10s.
    expect(stoppedAt).toBe(600);
    expect(stoppedAt / TICKS_PER_SECOND).toBeCloseTo(DEFAULT_SPIN_TIME, 6);
  });

  it('matches spinTime within one tick for non-round durations', () => {
    const spinTime = 7.37;
    const phys = WheelPhysics.spin({ targetFinalAngle: 5, segments: 5, spinTime });
    const { stoppedAt } = runToStop(phys);
    expect(Math.abs(stoppedAt / TICKS_PER_SECOND - spinTime)).toBeLessThanOrEqual(1 / TICKS_PER_SECOND);
  });
});

describe('WheelPhysics deterministic landing', () => {
  it('lands exactly on targetFinalAngle', () => {
    const target = 123.456;
    const phys = WheelPhysics.spin({ targetFinalAngle: target, segments: 7 });
    const { results } = runToStop(phys);
    const final = results[results.length - 1];
    expect(final.justStopped).toBe(true);
    expect(final.phase).toBe('stopped');
    expect(final.angle).toBeCloseTo(target, 6);
    expect(final.speed).toBe(0);
  });

  it('decelStart is targetFinalAngle - D so the simulated decel sums to D', () => {
    const phys = WheelPhysics.spin({ targetFinalAngle: 50, segments: 6 });
    const D = phys.decelRotationConstant;
    const closed = decelRotation(phys.peakSpeed, phys.decayPerTick, phys.decelTickCount);
    expect(D).toBeCloseTo(closed, 9);

    // Simulate the decel phase in isolation and confirm the rotation equals D.
    for (let i = 0; i < phys.accelTickCount; i++) phys.tick();
    let angleAtDecelStart: number | null = null;
    let angleAtStop = 0;
    for (;;) {
      const before = phys.angle;
      const r = phys.tick();
      if (angleAtDecelStart == null) angleAtDecelStart = before; // pre-jump not counted
      angleAtStop = r.angle;
      if (r.justStopped) break;
    }
    // The very first decel tick applies the discard-jump, so measure from the
    // known decelStart (targetFinalAngle - D).
    expect(angleAtStop - (50 - D)).toBeCloseTo(D, 6);
  });
});

describe('WheelPhysics winner lands under the pointer (property test)', () => {
  it('stops on the pre-chosen winner across many counts/indices/jitters', () => {
    const jitters = [-0.45, -0.2, 0, 0.15, 0.4];
    for (const count of [2, 3, 6, 8, 12, 17, 30]) {
      for (let index = 0; index < count; index++) {
        const jitter = jitters[(index + count) % jitters.length];
        const targetMod = winnerAngleRad(index, count, jitter);
        const targetFinalAngle = targetMod + 8 * TWO_PI; // add whole turns
        const phys = WheelPhysics.spin({ targetFinalAngle, segments: count });
        const { results } = runToStop(phys);
        const finalDeg = results[results.length - 1].angle * RAD_TO_DEG;
        expect(pointerSegmentIndex(finalDeg, count)).toBe(index);
      }
    }
  });
});

describe('WheelPhysics boundary crossings', () => {
  it('emits a crossing count equal to total real rotation / slice', () => {
    const count = 8;
    const phys = WheelPhysics.spin({ targetFinalAngle: 200, segments: count });
    const A = accelRotation(phys.peakSpeed, phys.accelTickCount);
    const D = phys.decelRotationConstant;
    const slice = TWO_PI / count;
    const expected = Math.floor((A + D) / slice);
    const { totalCrossings } = runToStop(phys);
    expect(Math.abs(totalCrossings - expected)).toBeLessThanOrEqual(1);
  });

  it('does not count the discard-jump as crossings', () => {
    // A huge target would make the jump span many slices; crossings must still
    // track only real motion (A + D), not the jump.
    const count = 6;
    const phys = WheelPhysics.spin({ targetFinalAngle: 5000, segments: count });
    const A = accelRotation(phys.peakSpeed, phys.accelTickCount);
    const D = phys.decelRotationConstant;
    const slice = TWO_PI / count;
    const { totalCrossings } = runToStop(phys);
    expect(Math.abs(totalCrossings - Math.floor((A + D) / slice))).toBeLessThanOrEqual(1);
    // Sanity: the jump alone (5000/slice ~ 4700) is far larger than counted.
    expect(totalCrossings).toBeLessThan(Math.floor(5000 / slice));
  });
});

describe('WheelPhysics gentle (reduced-motion) mode', () => {
  it('is still a real spin (calmer peak, no blur) that lands exactly on the winner', () => {
    const count = 10;
    const index = 4;
    const targetMod = winnerAngleRad(index, count, 0.1);
    const targetFinalAngle = targetMod + 6 * TWO_PI;
    const phys = WheelPhysics.spin({ targetFinalAngle, segments: count, gentle: true });

    expect(phys.peakSpeed).toBeCloseTo(GENTLE_PEAK_SPEED, 9);
    expect(phys.decelTickCount).toBe(7 * TICKS_PER_SECOND);

    const { results, stoppedAt } = runToStop(phys);
    const final = results[results.length - 1];
    expect(final.angle).toBeCloseTo(targetFinalAngle, 6);
    expect(pointerSegmentIndex(final.angle * RAD_TO_DEG, count)).toBe(index);
    // Calmer than the normal (motion-blur) peak, but still a substantial spin.
    const maxSpeed = Math.max(...results.map((r) => r.speed));
    expect(maxSpeed).toBeLessThan(PEAK_SPEED);
    expect(maxSpeed).toBeGreaterThan(PEAK_SPEED / 2);
    // accel(60) + decel(420) = 480 ticks == 8s.
    expect(stoppedAt).toBe(8 * TICKS_PER_SECOND);
    // The whole point of the fix: reduced motion still rotates a real amount
    // (visible accel + decel), not the old ~0.5 revolution.
    const realRotation =
      accelRotation(phys.peakSpeed, phys.accelTickCount) + phys.decelRotationConstant;
    expect(realRotation / TWO_PI).toBeGreaterThan(5);
  });
});

describe('WheelPhysics.resolveTarget (minimal reset jump)', () => {
  it('lands the winner while keeping the accel->decel jump under one turn', () => {
    for (const gentle of [false, true]) {
      for (const count of [2, 6, 8, 17]) {
        for (const index of [0, 1, count - 1]) {
          const startAngle = 3.3; // arbitrary non-zero idle position
          const targetMod = winnerAngleRad(index, count, 0.2);
          const targetFinalAngle = WheelPhysics.resolveTarget({
            startAngle,
            targetMod,
            gentle,
          });
          const phys = WheelPhysics.spin({
            targetFinalAngle,
            segments: count,
            gentle,
            startAngle,
          });

          // Jump = decelStart - accelEnd must be a forward move of < 1 turn.
          const accelEnd = startAngle + accelRotation(phys.peakSpeed, phys.accelTickCount);
          const decelStart = targetFinalAngle - phys.decelRotationConstant;
          const jump = decelStart - accelEnd;
          expect(jump).toBeGreaterThanOrEqual(-1e-9);
          expect(jump).toBeLessThan(TWO_PI + 1e-9);

          // And it still lands on the pre-chosen winner.
          const { results } = runToStop(phys);
          const finalDeg = results[results.length - 1].angle * RAD_TO_DEG;
          expect(pointerSegmentIndex(finalDeg, count)).toBe(index);
        }
      }
    }
  });
});

describe('WheelPhysics normal spin revolutions', () => {
  it('travels ~9.3 real revolutions over 10s (wheelofnames feel)', () => {
    const phys = WheelPhysics.spin({ targetFinalAngle: 100, segments: 8 });
    const realRotation =
      accelRotation(phys.peakSpeed, phys.accelTickCount) + phys.decelRotationConstant;
    expect(realRotation / TWO_PI).toBeGreaterThan(9);
    expect(realRotation / TWO_PI).toBeLessThan(9.7);
  });
});

describe('WheelPhysics idle drift', () => {
  it('rotates continuously at the idle speed and never stops', () => {
    const phys = WheelPhysics.idle(6, 0);
    let last;
    for (let i = 0; i < 300; i++) last = phys.tick();
    expect(last!.phase).toBe('idle');
    expect(last!.speed).toBeCloseTo(IDLE_SPEED, 9);
    expect(last!.angle).toBeCloseTo(IDLE_SPEED * 300, 6);
    expect(last!.justStopped).toBe(false);
  });
});

describe('winnerAngleRad', () => {
  it('centers the winner under the pointer with no jitter', () => {
    for (const count of [2, 4, 6, 12]) {
      for (let i = 0; i < count; i++) {
        const deg = winnerAngleRad(i, count) * RAD_TO_DEG;
        expect(pointerSegmentIndex(deg, count)).toBe(i);
      }
    }
  });
  it('stays inside the winning slice even at extreme jitter', () => {
    const count = 8;
    for (const j of [-1, -0.5, 0.5, 1]) {
      const deg = winnerAngleRad(3, count, j) * RAD_TO_DEG;
      expect(pointerSegmentIndex(deg, count)).toBe(3);
    }
  });
});
