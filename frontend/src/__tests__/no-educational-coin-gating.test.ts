import { describe, expect, it } from 'vitest';
import fs from 'fs';
import path from 'path';

/**
 * R1 guard (companion architecture plan, WP00 audit risk R1).
 *
 * Hard rule: NOTHING educational is ever gated behind coins. Lessons, puzzles
 * and the learn routes must never check a coin balance or call the coin-spend
 * RPC — only cosmetics (the shop) may. This static test greps the educational
 * source paths and fails if any coin-spend / coin-balance token appears there,
 * so a future change that accidentally paywalls learning is caught in CI.
 *
 * ALLOWLIST (coin logic legitimately lives here, NOT scanned):
 *   - frontend/src/app/shop/**, frontend/src/app/api/gamification/shop/**
 *   - frontend/src/lib/gamification/** (store.ts buyItem, items.ts, etc.)
 *   - frontend/src/app/coins/**, frontend/src/app/api/gamification/coins/**
 *   - backend coin/gamification routes
 * These are cosmetic commerce, which the one-economy decision explicitly keeps.
 */

// Tokens that indicate coin spending / balance gating.
const FORBIDDEN = [
  'spend_coins',
  'spendCoins',
  'coin_balance',
  'coinBalance',
  'insufficient_balance',
  'buyItem',
];

const repoRoot = path.resolve(__dirname, '../../..');
const frontendRoot = path.resolve(__dirname, '..'); // frontend/src

// Educational code paths to scan.
const EDUCATIONAL_DIRS = [path.join(frontendRoot, 'app', 'learn')];
const EDUCATIONAL_FILES = [
  path.join(repoRoot, 'backend', 'api', 'lessons.py'),
  path.join(repoRoot, 'backend', 'api', 'puzzles.py'),
];

function walk(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  const out: string[] = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      out.push(...walk(full));
    } else if (/\.(ts|tsx|js|jsx)$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

function collectEducationalFiles(): string[] {
  const files = EDUCATIONAL_DIRS.flatMap(walk);
  for (const f of EDUCATIONAL_FILES) {
    if (fs.existsSync(f)) files.push(f);
  }
  return files;
}

describe('R1 guard — no educational coin-gating', () => {
  const files = collectEducationalFiles();

  it('finds educational source files to scan', () => {
    // Guards against a silent pass if the paths ever move.
    expect(files.length).toBeGreaterThan(0);
  });

  it.each(files)('%s has no coin-spend / balance gating', (file) => {
    const source = fs.readFileSync(file, 'utf-8');
    const hits = FORBIDDEN.filter((token) => source.includes(token));
    expect(
      hits,
      `Educational path must never coin-gate learning, but ${path.relative(
        repoRoot,
        file,
      )} references: ${hits.join(', ')}. If this is cosmetic commerce it does not belong in an educational path.`,
    ).toEqual([]);
  });
});
