// Cryptographically-random, uniform segment selection for the wheel.

/**
 * A source of random 32-bit unsigned integers. Defaults to
 * `crypto.getRandomValues`; injectable for deterministic tests.
 */
export type RandomUint32 = () => number;

function cryptoUint32(): number {
  const buf = new Uint32Array(1);
  crypto.getRandomValues(buf);
  return buf[0];
}

/**
 * Pick a uniformly-random index in [0, count). Uses rejection sampling to avoid
 * modulo bias, so every segment has exactly equal probability.
 */
export function pickIndex(count: number, rng: RandomUint32 = cryptoUint32): number {
  if (!Number.isInteger(count) || count <= 0) {
    throw new Error('pickIndex: count must be a positive integer');
  }
  if (count === 1) return 0;

  const range = 0x100000000; // 2^32
  // Largest multiple of `count` that fits in a uint32; values >= limit are
  // rejected to keep the distribution uniform.
  const limit = range - (range % count);
  let x = rng() >>> 0;
  while (x >= limit) {
    x = rng() >>> 0;
  }
  return x % count;
}
