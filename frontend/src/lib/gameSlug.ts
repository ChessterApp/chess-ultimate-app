/**
 * gameSlug — opaque slug codec for shareable master-database game links.
 *
 * A slug encodes `[sourceEnum, id]` where sourceEnum is 0 = twic, 1 = lichess.
 * It is emitted as an alphanumeric string via sqids with a custom shuffled
 * alphabet, so the underlying data source name is never exposed in the URL.
 *
 * Decoding is strict: any slug that does not round-trip back to the exact same
 * values it claims to encode returns null, so garbage input can't resolve to a
 * real game.
 */
import Sqids from 'sqids';

export type GameSource = 'twic' | 'lichess';

// Ordered enum — index is what gets encoded. Never reorder (would break links).
const SOURCES: GameSource[] = ['twic', 'lichess'];

// Custom shuffled alphabet. Built from base62 via a fixed-seed Fisher–Yates
// shuffle so every character is unique (a sqids requirement) and the result is
// alphanumeric only — emitted slugs therefore contain no source names.
function buildAlphabet(): string {
  const base = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');
  let seed = 0x5f3759df; // fixed seed → deterministic, stable across sessions
  for (let i = base.length - 1; i > 0; i--) {
    // xorshift32 PRNG, seeded constant → reproducible permutation
    seed ^= seed << 13; seed ^= seed >>> 17; seed ^= seed << 5;
    const j = (seed >>> 0) % (i + 1);
    [base[i], base[j]] = [base[j], base[i]];
  }
  return base.join('');
}

const sqids = new Sqids({
  alphabet: buildAlphabet(),
  minLength: 7,
});

export function encodeGameSlug(source: GameSource, id: number): string {
  const sourceEnum = SOURCES.indexOf(source);
  if (sourceEnum < 0 || !Number.isInteger(id) || id < 0) {
    throw new Error(`Invalid game slug input: source=${source} id=${id}`);
  }
  return sqids.encode([sourceEnum, id]);
}

export function decodeGameSlug(slug: string): { source: GameSource; id: number } | null {
  if (!slug || typeof slug !== 'string') return null;
  let decoded: number[];
  try {
    decoded = sqids.decode(slug);
  } catch {
    return null;
  }
  if (decoded.length !== 2) return null;
  const [sourceEnum, id] = decoded;
  const source = SOURCES[sourceEnum];
  if (!source || !Number.isInteger(id) || id < 0) return null;

  // Strict round-trip: re-encode the decoded values and require an exact match.
  // sqids can decode multiple strings to the same numbers; this rejects any
  // slug that isn't the canonical encoding of these values.
  if (encodeGameSlug(source, id) !== slug) return null;

  return { source, id };
}
