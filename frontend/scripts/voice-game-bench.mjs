#!/usr/bin/env node
/**
 * voice-game-bench — a whole game against the coach by voice, the way the browser runs it: the
 * Live model gets Hermes' voice prompt and tools (start_game / make_game_move among them, 2026-10-12)
 * and every tool runs on a local Hermes through /api/coach/tool with the session and the student's
 * last words, as the site sends them. The student's turns are spoken with macOS `say` and streamed
 * in real time.
 *
 *   cd frontend
 *   node scripts/voice-game-bench.mjs --hermes http://127.0.0.1:8690 --runs 2 --out /tmp/vg
 *
 * Needs: GEMINI_API_KEY (env or ../hermes/.env), Hermes on --hermes with its puzzle/engine set
 * up, macOS `say` (voice Milena) + ffmpeg.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { GoogleGenAI, Modality } from '@google/genai';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FRONT = path.resolve(HERE, '..');
const REPO = path.resolve(FRONT, '..');

// What 3.1 gets in production (VOICE_CORE_TOOLS in the live-token route).
const CORE = new Set(['board_control', 'analyze_position', 'get_position_stats', 'get_opening_stats',
  'search_master_games', 'get_game_pgn', 'compare_variations', 'score_position_themes', 'check_moves',
  'get_puzzle', 'get_topic', 'list_topics', 'get_lesson', 'get_learning_path', 'lookup_opening', 'review_game',
  'start_game', 'make_game_move', 'famous_game']);
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const IN_RATE = 16000;
const CHUNK_MS = 20;
const TURN_TIMEOUT_MS = 45000;
const IDLE_AFTER_TURN_MS = 2500;

// The student's side of the conversation (Alexander's game, 10.10: 1.e4 d5 2.exd5 …).
const SCRIPT = [
  'Спорим, я тебя обыграю? Давай сыграем партию, я за белых.',
  'Пешка е четыре.',
  'Беру пешку на дэ пять.',
  'Конь эф три.',
  'А где твоя пешка?',
];

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : def;
}
const HERMES = arg('hermes', 'http://127.0.0.1:8690');
const MODEL = arg('model', 'gemini-3.1-flash-live-preview');
const RUNS = Number(arg('runs', '1'));
const OUT = arg('out', path.join(os.tmpdir(), 'voice-game-bench'));
const VOICE = arg('voice', 'Milena');

function key() {
  if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY;
  const m = fs.readFileSync(path.join(REPO, 'hermes/.env'), 'utf8').match(/^GEMINI_API_KEY=(.*)$/m);
  if (!m) throw new Error('GEMINI_API_KEY not set');
  return m[1].trim().replace(/^['"]|['"]$/g, '');
}

function synth(text) {
  const dir = path.join(os.tmpdir(), 'voice-game-bench-audio');
  fs.mkdirSync(dir, { recursive: true });
  const pcm = path.join(dir, `${Buffer.from(`${VOICE}:${text}`).toString('base64url').slice(0, 80)}.pcm`);
  if (!fs.existsSync(pcm)) {
    const aiff = `${pcm}.aiff`;
    execFileSync('say', ['-v', VOICE, '-o', aiff, text]);
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', aiff, '-ar', String(IN_RATE), '-ac', '1', '-f', 's16le', pcm]);
    fs.rmSync(aiff);
  }
  return fs.readFileSync(pcm);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function hermes(pathname, body, method = 'POST', user = 'voice-game-bench') {
  const res = await fetch(`${HERMES}${pathname}`, {
    method,
    headers: { 'Content-Type': 'application/json', 'X-User-Id': user, 'x-subscription-tier': 'pro' },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(90000),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail?.detail || data?.detail || `Hermes ${res.status}`);
  return data;
}

async function run(ai, n) {
  const user = `voice-game-bench-${n}`;
  const sid = (await hermes('/api/coach/sessions', {}, 'POST', user)).id;
  const prompt = await hermes('/api/coach/voice/prompt', { fen: START, locale: 'ru', tools_available: true }, 'POST', user);
  const hermesTools = ((await hermes('/api/coach/tools', undefined, 'GET', user)).tools || []).filter((t) => CORE.has(t.name));
  const config = {
    responseModalities: [Modality.AUDIO],
    systemInstruction: prompt.system_prompt,
    inputAudioTranscription: { languageCodes: ['ru-RU', 'kk-KZ', 'en-US'] },
    outputAudioTranscription: {},
    tools: [{ functionDeclarations: hermesTools }],
    thinkingConfig: { thinkingBudget: 0 },
  };

  let game = null;  // the last game state a tool returned
  const log = [];
  let turn = null;
  let idleTimer = null;
  let resolveTurn = () => {};
  const endTurnSoon = () => {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(() => resolveTurn(), IDLE_AFTER_TURN_MS);
  };

  async function onTool(session, calls) {
    const responses = [];
    for (const fc of calls) {
      let response;
      try {
        const body = await hermes(`/api/coach/tool/${encodeURIComponent(fc.name)}`,
          { args: fc.args ?? {}, session_id: sid, utterance: turn.heard.trim() || undefined }, 'POST', user);
        response = body.error ? { error: body.error } : { result: body.result ?? body };
        const g = (body.board_actions || []).find((a) => a.type === 'game');
        if (g) game = g.game;
      } catch (err) {
        response = { error: String(err.message || err) };
      }
      turn.tools.push({ name: fc.name, args: fc.args, response });
      responses.push({ id: fc.id, name: fc.name, response });
    }
    session.sendToolResponse({ functionResponses: responses });
  }

  let session;
  const step = (x) => process.env.VGB_DEBUG && console.error(`[vgb] ${x}`);
  step('connecting');
  let closedEarly = null;
  const connecting = ai.live.connect({
    model: MODEL,
    config,
    callbacks: {
      onmessage: (m) => {
        if (!turn) return;
        if (m.toolCall?.functionCalls?.length) {
          clearTimeout(idleTimer);
          void onTool(session, m.toolCall.functionCalls);
        }
        const sc = m.serverContent;
        if (!sc) return;
        if (sc.inputTranscription?.text) turn.heard += sc.inputTranscription.text;
        if (sc.outputTranscription?.text) {
          turn.said += sc.outputTranscription.text;
          clearTimeout(idleTimer);
        }
        if (sc.turnComplete) endTurnSoon();
      },
      onopen: () => step('open'),
      onerror: (e) => {
        step(`error ${e?.message}`);
        log.push({ error: e?.message });
      },
      onclose: (e) => {
        step(`close ${e?.code} ${e?.reason}`);
        log.push({ closed: e?.code, reason: e?.reason });
        closedEarly?.(new Error(`Live closed ${e?.code}: ${e?.reason}`));
        resolveTurn();
      },
    },
  });
  // A session closed during setup (no credits, a bad model) never resolves connect().
  session = await Promise.race([connecting, new Promise((_, reject) => { closedEarly = reject; })]);
  closedEarly = null;
  session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: `Current position (FEN): ${START}` }] }], turnComplete: false });

  step('connected');
  for (const line of SCRIPT) {
    step(`say: ${line}`);
    turn = { student: line, heard: '', said: '', tools: [] };
    const done = new Promise((r) => {
      resolveTurn = r;
    });
    const pcm = synth(line);
    const bytes = (IN_RATE * 2 * CHUNK_MS) / 1000;
    const silence = Buffer.alloc(bytes);
    const t0 = Date.now();
    let sent = 0;
    let finished = false;
    void done.then(() => {
      finished = true;
    });
    for (let i = 0; !finished && Date.now() - t0 < TURN_TIMEOUT_MS; i++) {
      const wait = t0 + i * CHUNK_MS - Date.now();
      if (wait > 0) await sleep(wait);
      let chunk = silence;
      if (sent < pcm.length) {
        chunk = pcm.subarray(sent, sent + bytes);
        sent += chunk.length;
      }
      try {
        session.sendRealtimeInput({ audio: { data: chunk.toString('base64'), mimeType: `audio/pcm;rate=${IN_RATE}` } });
      } catch {
        break;
      }
    }
    turn.board = game ? { fen: game.fen, moves: game.moves, status: game.status } : null;
    turn.timeout = !finished;
    log.push(turn);
  }
  try {
    session.close();
  } catch {
    /* closing */
  }
  return log;
}

const ai = new GoogleGenAI({ apiKey: key(), httpOptions: { apiVersion: 'v1alpha' } });
fs.mkdirSync(OUT, { recursive: true });
for (let n = 0; n < RUNS; n++) {
  const log = await run(ai, n);
  fs.writeFileSync(path.join(OUT, `run${n}.json`), JSON.stringify(log, null, 1));
  console.log(`\n===== run ${n}`);
  for (const t of log) {
    if (!t.student) {
      console.log(JSON.stringify(t));
      continue;
    }
    console.log(`\nУЧЕНИК: ${t.student}\n  услышано: ${t.heard.trim()}`);
    for (const x of t.tools) console.log(`  ⚙ ${x.name}(${JSON.stringify(x.args)}) → ${JSON.stringify(x.response).slice(0, 220)}`);
    console.log(`  ТРЕНЕР: ${t.said.trim()}`);
    console.log(`  доска: ${t.board ? `${t.board.moves.join(' ')} [${t.board.status}]` : 'нет партии'}${t.timeout ? '  (TIMEOUT)' : ''}`);
  }
}
