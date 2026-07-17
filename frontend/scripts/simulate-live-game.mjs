#!/usr/bin/env node
/**
 * simulate-live-game.mjs — end-to-end, API-level simulation of the online-play
 * (live-games) feature against PRODUCTION (https://chesster.io).
 *
 * What it proves, entirely over HTTP (no browser):
 *   1. Two Clerk test users are authenticated via the Backend API (sign-in
 *      tokens) exchanged for real session JWTs at the Frontend API.
 *   2. The full challenge → join → play → checkmate flow works, with the
 *      server rejecting an unauthenticated caller, a self-join, an illegal
 *      move, and an out-of-turn move.
 *   3. A second game ends by resignation.
 *   4. The Supabase `games` / `game_moves` rows are consistent, then removed.
 *
 * All secrets are read from frontend/.env.local at runtime — nothing is
 * printed or hard-coded. Prints `PASS`/`FAIL` per assertion and exits non-zero
 * on any failure.
 *
 * Usage:  node frontend/scripts/simulate-live-game.mjs
 * Node 22, plain fetch. chess.js is available from frontend deps if needed.
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ENV_PATH = path.resolve(__dirname, '..', '.env.local');
const BASE = process.env.SIM_BASE_URL || 'https://chesster.io';
const CLERK_JS_VERSION = '5.40.0';

// ── env ──────────────────────────────────────────────────────────────────────
const envText = fs.readFileSync(ENV_PATH, 'utf8');
const env = (key) => {
  const m = envText.match(new RegExp('^' + key + '=(.*)$', 'm'));
  return m ? m[1].trim() : undefined;
};
const SK = env('CLERK_SECRET_KEY');
const PK = env('NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY');
const SB_URL = env('NEXT_PUBLIC_SUPABASE_URL');
const SB_KEY = env('SUPABASE_SERVICE_ROLE_KEY');
for (const [k, v] of Object.entries({ CLERK_SECRET_KEY: SK, NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY: PK, NEXT_PUBLIC_SUPABASE_URL: SB_URL, SUPABASE_SERVICE_ROLE_KEY: SB_KEY })) {
  if (!v) { console.error(`FATAL: missing ${k} in ${ENV_PATH}`); process.exit(2); }
}

// FAPI domain is base64-encoded in the publishable key: pk_live_<base64("clerk.chesster.io$")>.
const FAPI = 'https://' + Buffer.from(PK.replace(/^pk_(live|test)_/, ''), 'base64').toString('utf8').replace(/\$$/, '');
const BAPI = 'https://api.clerk.com/v1';

const bapiHeaders = { Authorization: `Bearer ${SK}`, 'Content-Type': 'application/json' };
const sbHeaders = { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, 'Content-Type': 'application/json' };

// ── assertion framework ────────────────────────────────────────────────────────
let passed = 0;
let failed = 0;
function assert(cond, msg) {
  if (cond) { passed++; console.log(`PASS  ${msg}`); }
  else { failed++; console.log(`FAIL  ${msg}`); }
  return !!cond;
}

// ── Clerk auth ─────────────────────────────────────────────────────────────────
async function findOrCreateUser(email) {
  let r = await fetch(`${BAPI}/users?email_address=${encodeURIComponent(email)}`, { headers: bapiHeaders });
  const list = await r.json();
  if (Array.isArray(list) && list.length) return list[0];
  // Deterministic password so re-runs of create (should the lookup ever miss) succeed;
  // these are throwaway test accounts kept for regression runs.
  r = await fetch(`${BAPI}/users`, {
    method: 'POST',
    headers: bapiHeaders,
    body: JSON.stringify({
      email_address: [email],
      password: `Chesster-Sim-${email.split('@')[0]}-2026!`,
      skip_password_checks: true,
    }),
  });
  const created = await r.json();
  if (!r.ok) throw new Error(`create user failed (${email}): ${JSON.stringify(created)}`);
  return created;
}

/**
 * A minimal Clerk session for one test user. Mints a sign-in token via the
 * Backend API and exchanges it for a session JWT at the Frontend API, then
 * refreshes the (short-lived) JWT on demand.
 */
class Session {
  constructor(userId, label) {
    this.userId = userId;
    this.label = label;
    this.sid = null;
    this.clientCookie = null;
    this.jwt = null;
    this.jwtAt = 0;
  }

  async init() {
    // 1) sign-in token (Backend API)
    let r = await fetch(`${BAPI}/sign_in_tokens`, {
      method: 'POST', headers: bapiHeaders, body: JSON.stringify({ user_id: this.userId }),
    });
    const sit = await r.json();
    if (!r.ok || !sit.token) throw new Error(`sign_in_tokens failed (${this.label}): ${JSON.stringify(sit)}`);

    // 2) exchange the ticket at the Frontend API → creates a session
    r = await fetch(`${FAPI}/v1/client/sign_ins?_clerk_js_version=${CLERK_JS_VERSION}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded', Origin: BASE },
      body: new URLSearchParams({ strategy: 'ticket', ticket: sit.token }),
    });
    const setCookie = r.headers.get('set-cookie') || '';
    const signIn = await r.json();
    if (signIn?.response?.status !== 'complete') {
      throw new Error(`sign_ins not complete (${this.label}): ${JSON.stringify(signIn?.response ?? signIn)}`);
    }
    this.clientCookie = setCookie.match(/__client=([^;]+)/)?.[1] ?? null;
    this.sid = signIn.response.created_session_id;
    const sessions = signIn.client?.sessions ?? [];
    const sess = sessions.find((s) => s.id === this.sid) ?? sessions[0];
    this.jwt = sess?.last_active_token?.jwt ?? null;
    this.jwtAt = Date.now();
    if (!this.jwt) throw new Error(`no session JWT minted (${this.label})`);
    return this;
  }

  /** Return a fresh-enough session JWT, refreshing via FAPI when it ages out. */
  async token() {
    if (this.jwt && Date.now() - this.jwtAt < 40_000) return this.jwt;
    try {
      const r = await fetch(`${FAPI}/v1/client/sessions/${this.sid}/tokens?_clerk_js_version=${CLERK_JS_VERSION}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          Origin: BASE,
          ...(this.clientCookie ? { Cookie: `__client=${this.clientCookie}` } : {}),
        },
      });
      const body = await r.json();
      if (r.ok && body?.jwt) { this.jwt = body.jwt; this.jwtAt = Date.now(); return this.jwt; }
    } catch {
      /* fall through to full re-init */
    }
    await this.init();
    return this.jwt;
  }
}

// ── live-games API helper ──────────────────────────────────────────────────────
async function api(method, apiPath, { session, body } = {}) {
  const headers = { 'Content-Type': 'application/json' };
  if (session) headers.Authorization = `Bearer ${await session.token()}`;
  const r = await fetch(`${BASE}${apiPath}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let json = null;
  const text = await r.text();
  try { json = text ? JSON.parse(text) : null; } catch { json = text; }
  return { status: r.status, json };
}

// ── Supabase helper ────────────────────────────────────────────────────────────
async function sb(method, query, { body, prefer } = {}) {
  const r = await fetch(`${SB_URL}/rest/v1/${query}`, {
    method,
    headers: { ...sbHeaders, ...(prefer ? { Prefer: prefer } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  let json = null;
  const text = await r.text();
  try { json = text ? JSON.parse(text) : null; } catch { json = text; }
  return { status: r.status, json };
}

// ── flow ───────────────────────────────────────────────────────────────────────
const WHITE_EMAIL = 'chesster-sim-white@test.chesster.io';
const BLACK_EMAIL = 'chesster-sim-black@test.chesster.io';

/** GET hydration and assert the reported status/ply/fen match expectations. */
async function assertState(gameId, session, expect, label) {
  const { status, json } = await api('GET', `/api/live-games/${gameId}`, { session });
  const g = json?.game ?? {};
  let ok = status === 200 && g.status === expect.status;
  if (expect.ply !== undefined) ok = ok && g.ply === expect.ply;
  if (expect.fen !== undefined) ok = ok && g.fen === expect.fen;
  if (expect.result !== undefined) ok = ok && g.result === expect.result;
  if (expect.winnerId !== undefined) ok = ok && g.winnerId === expect.winnerId;
  if (expect.endReason !== undefined) ok = ok && g.endReason === expect.endReason;
  assert(ok, `${label} — GET state status=${g.status} ply=${g.ply}${expect.result !== undefined ? ` result=${g.result}` : ''}`);
  return json;
}

async function main() {
  console.log(`\n=== live-game simulation against ${BASE} ===`);
  console.log(`FAPI: ${FAPI}\n`);

  const createdGameIds = [];
  try {
    // Users + sessions
    const [whiteUser, blackUser] = await Promise.all([
      findOrCreateUser(WHITE_EMAIL),
      findOrCreateUser(BLACK_EMAIL),
    ]);
    const whiteId = whiteUser.id;
    const blackId = blackUser.id;
    assert(!!whiteId && !!blackId && whiteId !== blackId, `two distinct Clerk test users (${whiteId} / ${blackId})`);
    const A = await new Session(whiteId, 'white').init();
    const B = await new Session(blackId, 'black').init();
    assert(!!A.jwt && !!B.jwt, 'minted session JWTs for both users');

    // ── Regression guard: unauthenticated challenge → 401 ──
    {
      const { status } = await api('POST', '/api/live-games/challenge', { body: { colorChoice: 'white', initialSec: 300, incrementSec: 0 } });
      assert(status === 401, `unauthenticated challenge rejected (got ${status}, want 401)`);
    }

    // ── GAME 1: Scholar's Mate ──────────────────────────────────────────────
    console.log('\n--- Game 1: Scholar\'s Mate ---');
    // A (white) creates a 5+0 blitz challenge.
    let res = await api('POST', '/api/live-games/challenge', { session: A, body: { colorChoice: 'white', initialSec: 300, incrementSec: 0 } });
    const g1 = res.json?.gameId;
    if (g1) createdGameIds.push(g1);
    assert(res.status === 201 && !!g1 && res.json?.url?.endsWith(`/play/live/${g1}`), `A created challenge → gameId + link (status ${res.status})`);

    await assertState(g1, A, { status: 'challenge', ply: 0 }, 'game1 challenge');

    // A tries to join their own game → 403.
    res = await api('POST', `/api/live-games/${g1}/join`, { session: A });
    assert(res.status === 403 && res.json?.error === 'cannot_join_own', `A self-join rejected (got ${res.status} ${res.json?.error})`);

    // B joins → active, colors + clocks assigned.
    res = await api('POST', `/api/live-games/${g1}/join`, { session: B });
    const okJoin = res.status === 200 && res.json?.status === 'active' &&
      res.json?.whiteId === whiteId && res.json?.blackId === blackId &&
      res.json?.whiteMs === 300_000 && res.json?.blackMs === 300_000;
    assert(okJoin, `B joined → active, white=A black=B, clocks 300000/300000 (status ${res.status})`);
    await assertState(g1, A, { status: 'active', ply: 0 }, 'game1 after join');

    // Illegal move: white plays e2e5 → 422.
    res = await api('POST', `/api/live-games/${g1}/move`, { session: A, body: { uci: 'e2e5' } });
    assert(res.status === 422 && res.json?.error === 'illegal_move', `illegal move e2e5 rejected (got ${res.status} ${res.json?.error})`);

    // 1. e4
    res = await api('POST', `/api/live-games/${g1}/move`, { session: A, body: { uci: 'e2e4' } });
    assert(res.status === 200 && res.json?.san === 'e4' && res.json?.ply === 1, `1. e4 accepted (san ${res.json?.san})`);
    await assertState(g1, A, { status: 'active', ply: 1 }, 'game1 after 1.e4');

    // Out-of-turn: white (right user) tries to move again on black's turn → 403.
    res = await api('POST', `/api/live-games/${g1}/move`, { session: A, body: { uci: 'f1c4' } });
    assert(res.status === 403 && res.json?.error === 'not_your_turn', `out-of-turn move by white rejected (got ${res.status} ${res.json?.error})`);

    // Remaining Scholar's Mate moves, alternating sessions.
    const line = [
      [B, 'e7e5', 'e5', 2],
      [A, 'f1c4', 'Bc4', 3],
      [B, 'b8c6', 'Nc6', 4],
      [A, 'd1h5', 'Qh5', 5],
      [B, 'g8f6', 'Nf6', 6],
    ];
    for (const [who, uci, san, ply] of line) {
      res = await api('POST', `/api/live-games/${g1}/move`, { session: who, body: { uci } });
      assert(res.status === 200 && res.json?.san === san && res.json?.ply === ply, `${ply}. ${san} accepted (${who.label})`);
      await assertState(g1, A, { status: 'active', ply }, `game1 after ${san}`);
    }

    // 4. Qxf7# — checkmate, white (A) wins.
    res = await api('POST', `/api/live-games/${g1}/move`, { session: A, body: { uci: 'h5f7' } });
    const okMate = res.status === 200 && res.json?.san === 'Qxf7#' && res.json?.gameOver?.result === '1-0' && res.json?.gameOver?.reason === 'checkmate';
    assert(okMate, `Qxf7# → checkmate 1-0 (san ${res.json?.san}, over ${JSON.stringify(res.json?.gameOver)})`);
    await assertState(g1, A, { status: 'finished', ply: 7, result: '1-0', winnerId: whiteId, endReason: 'checkmate' }, 'game1 finished');

    // ── GAME 2: resignation ─────────────────────────────────────────────────
    console.log('\n--- Game 2: resignation ---');
    res = await api('POST', '/api/live-games/challenge', { session: A, body: { colorChoice: 'white', initialSec: 300, incrementSec: 0 } });
    const g2 = res.json?.gameId;
    if (g2) createdGameIds.push(g2);
    assert(res.status === 201 && !!g2, `A created game 2 (status ${res.status})`);

    res = await api('POST', `/api/live-games/${g2}/join`, { session: B });
    assert(res.status === 200 && res.json?.status === 'active' && res.json?.whiteId === whiteId && res.json?.blackId === blackId, `B joined game 2 → active (status ${res.status})`);

    res = await api('POST', `/api/live-games/${g2}/move`, { session: A, body: { uci: 'e2e4' } });
    assert(res.status === 200 && res.json?.ply === 1, `game2 1. e4 (status ${res.status})`);
    res = await api('POST', `/api/live-games/${g2}/move`, { session: B, body: { uci: 'e7e5' } });
    assert(res.status === 200 && res.json?.ply === 2, `game2 1... e5 (status ${res.status})`);
    await assertState(g2, A, { status: 'active', ply: 2 }, 'game2 after 2 moves');

    // B (black) resigns → white (A) wins by resignation.
    res = await api('POST', `/api/live-games/${g2}/resign`, { session: B });
    const okResign = res.status === 200 && res.json?.result === '1-0' && res.json?.winnerId === whiteId && res.json?.reason === 'resign' && res.json?.status === 'finished';
    assert(okResign, `B resigned → 1-0 for white, reason resign (status ${res.status})`);
    await assertState(g2, A, { status: 'finished', ply: 2, result: '1-0', winnerId: whiteId, endReason: 'resign' }, 'game2 finished');

    // ── Supabase verification ───────────────────────────────────────────────
    console.log('\n--- Supabase verification ---');
    // Game 1: finished, checkmate, 7 move rows (plies 1..7), players correct.
    let q = await sb('GET', `games?id=eq.${g1}&select=status,result,winner_id,end_reason,white_id,black_id,creator_id,opponent_id,ply`);
    let row = Array.isArray(q.json) ? q.json[0] : null;
    assert(!!row && row.status === 'finished' && row.result === '1-0' && row.winner_id === whiteId && row.end_reason === 'checkmate' &&
      row.white_id === whiteId && row.black_id === blackId && row.creator_id === whiteId && row.opponent_id === blackId && row.ply === 7,
      `game1 row consistent (status=${row?.status} result=${row?.result} reason=${row?.end_reason})`);
    q = await sb('GET', `game_moves?game_id=eq.${g1}&select=ply&order=ply.asc`);
    const plies1 = Array.isArray(q.json) ? q.json.map((m) => m.ply) : [];
    assert(plies1.length === 7 && plies1.every((p, i) => p === i + 1), `game1 has 7 move rows, plies 1..7 (got ${plies1.length})`);

    // Game 2: finished, resign, 2 move rows.
    q = await sb('GET', `games?id=eq.${g2}&select=status,result,winner_id,end_reason,white_id,black_id,ply`);
    row = Array.isArray(q.json) ? q.json[0] : null;
    assert(!!row && row.status === 'finished' && row.result === '1-0' && row.winner_id === whiteId && row.end_reason === 'resign' &&
      row.white_id === whiteId && row.black_id === blackId && row.ply === 2,
      `game2 row consistent (status=${row?.status} result=${row?.result} reason=${row?.end_reason})`);
    q = await sb('GET', `game_moves?game_id=eq.${g2}&select=ply`);
    const plies2 = Array.isArray(q.json) ? q.json.map((m) => m.ply) : [];
    assert(plies2.length === 2, `game2 has 2 move rows (got ${plies2.length})`);

    return createdGameIds;
  } finally {
    // ── Cleanup: delete ONLY the rows this run created ───────────────────────
    console.log('\n--- Cleanup ---');
    for (const id of createdGameIds) {
      const moves = await sb('DELETE', `game_moves?game_id=eq.${id}`, { prefer: 'return=representation' });
      const game = await sb('DELETE', `games?id=eq.${id}`, { prefer: 'return=representation' });
      const movesDeleted = Array.isArray(moves.json) ? moves.json.length : 0;
      const gameDeleted = Array.isArray(game.json) ? game.json.length : 0;
      // Confirm the game row is truly gone.
      const check = await sb('GET', `games?id=eq.${id}&select=id`);
      const gone = Array.isArray(check.json) && check.json.length === 0;
      assert(gameDeleted === 1 && gone, `cleaned up game ${id} (${movesDeleted} moves, game gone=${gone})`);
    }
  }
}

main()
  .then(() => {
    console.log(`\n=== RESULT: ${passed} passed, ${failed} failed ===`);
    process.exit(failed === 0 ? 0 : 1);
  })
  .catch((err) => {
    console.error('\nFATAL:', err?.message || err);
    console.log(`\n=== RESULT: ${passed} passed, ${failed} failed (aborted) ===`);
    process.exit(1);
  });
