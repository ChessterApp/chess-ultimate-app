#!/usr/bin/env node
// Puzzle Rush board geometry check: every chessground piece must sit centred
// on its square (within 1px) across phone / iPad / desktop widths, a rotation,
// and a hide → show cycle. Runs in WebKit and Chromium.
//
//   node scripts/verify-rush-board-geometry.mjs [baseUrl]   (default http://localhost:3000)
//
// Exits non-zero if any check fails.
import { execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import path from 'node:path';

async function loadPlaywright() {
  try {
    return await import('playwright');
  } catch {
    // Not a frontend dependency here: fall back to a global install.
    const root = execSync('npm root -g', { encoding: 'utf8' }).trim();
    return createRequire(import.meta.url)(path.join(root, 'playwright'));
  }
}

const BASE = (process.argv[2] || 'http://localhost:3000').replace(/\/$/, '');
const URL = `${BASE}/games/puzzlerush`;
const HEIGHT = 1100;
const WIDTHS = [390, 744, 810, 820, 834, 900, 1024, 1180, 1366];
const TOLERANCE = 1;

/** Max distance (px) between each piece's centre and its square's centre. */
async function measure(page) {
  return page.evaluate(() => {
    const board = [...document.querySelectorAll('cg-board')].find((b) => b.getBoundingClientRect().width > 0);
    if (!board) return { visible: false };
    const b = board.getBoundingClientRect();
    const sq = b.width / 8;
    let worst = 0;
    const pieces = [...board.querySelectorAll('piece')].filter((p) => !p.classList.contains('ghost'));
    for (const p of pieces) {
      // Position from the piece transform (chessground's own layout), size from its rect.
      const m = new DOMMatrixReadOnly(getComputedStyle(p).transform);
      const r = p.getBoundingClientRect();
      const cx = m.m41 + r.width / 2;
      const cy = m.m42 + r.height / 2;
      const sx = (Math.floor(cx / sq) + 0.5) * sq;
      const sy = (Math.floor(cy / sq) + 0.5) * sq;
      // Pieces sized for a different board also drift off the square centre.
      const sizeErr = Math.abs(r.width - sq) / 2;
      worst = Math.max(worst, Math.hypot(cx - sx, cy - sy), sizeErr);
    }
    return { visible: true, board: Math.round(b.width * 10) / 10, pieces: pieces.length, worst };
  });
}

async function settle(page) {
  // Two frames: our redraw is rAF-throttled.
  await page.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForTimeout(150);
}

async function setHidden(page, hidden) {
  await page.evaluate((h) => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => (h ? 'hidden' : 'visible') });
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => h });
    document.dispatchEvent(new Event('visibilitychange'));
  }, hidden);
}

const rows = [];
function record(engine, check, viewport, res) {
  let ok;
  let note = '';
  if (!res.visible) {
    // The start-screen board is hidden on phones (≤768px) by design.
    ok = viewport.width <= 768;
    note = ok ? 'board hidden (mobile)' : 'board missing';
  } else {
    ok = res.pieces > 0 && res.worst <= TOLERANCE;
    note = res.pieces ? '' : 'no pieces';
  }
  rows.push({
    engine,
    check,
    viewport: `${viewport.width}x${viewport.height}`,
    board: res.visible ? res.board : '-',
    pieces: res.visible ? res.pieces : '-',
    'max off (px)': res.visible ? res.worst.toFixed(2) : '-',
    result: ok ? 'PASS' : 'FAIL',
    note,
  });
}

async function newPage(browser, viewport) {
  const page = await browser.newPage({ viewport });
  // Skip SyncBoundary's first-visit "Syncing your data..." gate (as for a
  // returning visitor) — PowerSync may never get ready in a local/CI env.
  await page.addInitScript(() => localStorage.setItem('chesster:initial_sync_done', 'true'));
  return page;
}

async function run(pw, engine) {
  const browser = await pw[engine].launch();
  try {
    const page = await newPage(browser, { width: 1366, height: HEIGHT });
    await page.goto(URL, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('cg-board piece', { state: 'attached', timeout: 60_000 });
    await settle(page);

    for (const width of WIDTHS) {
      const vp = { width, height: HEIGHT };
      await page.setViewportSize(vp);
      await settle(page);
      record(engine, 'resize', vp, await measure(page));
    }

    // Fresh load at an iPad width: the first layout must already be right.
    const fresh = await newPage(browser, { width: 820, height: 1180 });
    await fresh.goto(URL, { waitUntil: 'domcontentloaded' });
    await fresh.waitForSelector('cg-board piece', { state: 'attached', timeout: 60_000 });
    await settle(fresh);
    record(engine, 'fresh load', { width: 820, height: 1180 }, await measure(fresh));
    await fresh.close();

    // Rotation: portrait ↔ landscape.
    for (const vp of [{ width: 820, height: 1180 }, { width: 1180, height: 820 }, { width: 820, height: 1180 }]) {
      await page.setViewportSize(vp);
      await page.evaluate(() => window.dispatchEvent(new Event('orientationchange')));
      await settle(page);
      record(engine, 'rotate', vp, await measure(page));
    }

    // Hide, resize while hidden (app switch / Split View), then show.
    await page.setViewportSize({ width: 1366, height: HEIGHT });
    await settle(page);
    await setHidden(page, true);
    const hiddenVp = { width: 834, height: 1194 };
    await page.setViewportSize(hiddenVp);
    await setHidden(page, false);
    await settle(page);
    record(engine, 'hide/show', hiddenVp, await measure(page));
  } finally {
    await browser.close();
  }
}

const pw = await loadPlaywright();
for (const engine of ['webkit', 'chromium']) {
  try {
    await run(pw, engine);
  } catch (err) {
    rows.push({ engine, check: 'run', viewport: '-', board: '-', pieces: '-', 'max off (px)': '-', result: 'FAIL', note: String(err.message || err).split('\n')[0] });
  }
}

console.log(`Puzzle Rush board geometry — ${URL} (tolerance ${TOLERANCE}px)`);
console.table(rows);
const failed = rows.filter((r) => r.result !== 'PASS').length;
console.log(failed ? `FAIL: ${failed}/${rows.length} checks failed` : `PASS: ${rows.length}/${rows.length} checks`);
process.exit(failed ? 1 : 0);
