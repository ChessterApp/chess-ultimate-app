#!/usr/bin/env node
/**
 * voice-bench — measure the Gemini Live voice coach end to end, the way the
 * browser runs it (same @google/genai SDK, same prompt and tools from Hermes).
 *
 * Each case is a spoken question synthesised with macOS `say`, streamed in real
 * time as 16 kHz PCM, followed by mic-like silence. Tool calls are executed on a
 * local Hermes (`POST /api/coach/tool/{name}`), exactly what /api/coach/tool
 * proxies to in production. Timings are measured from the end of speech.
 *
 *   cd frontend
 *   node scripts/voice-bench.mjs --model gemini-3.8-live --label 38-default
 *   node scripts/voice-bench.mjs --model gemini-3.1-flash-live-preview --vad fast --tools all
 *
 * Needs: GEMINI_API_KEY (env or ../hermes/.env), Hermes on --hermes
 * (hermes/scripts/coach_local.sh), macOS `say` + ffmpeg for the audio.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { GoogleGenAI, Modality } from '@google/genai';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '../..');

// Mirrors VOICE_TOOL_ALLOWLIST in src/app/api/coach/live-token/route.ts.
const PROD_VOICE_TOOLS = new Set([
  'board_control',
  'analyze_position',
  'get_position_stats',
  'get_opening_stats',
  'search_master_games',
  'get_game_pgn',
  'compare_variations',
  'score_position_themes',
  'check_moves',
  'get_puzzle',
]);

const IN_RATE = 16000;
const OUT_RATE = 24000;
const CHUNK_MS = 20;
const SPEECH_RMS = 0.02; // same threshold the browser hook uses for "user spoke"
const TURN_TIMEOUT_MS = 60000;
const SEGMENT_GAP_MS = 250;
const POST_TOOL_GRACE_MS = 6000;

// ── args ─────────────────────────────────────────────────────────────────────
function parseArgs(argv) {
  const a = {
    model: 'gemini-3.1-flash-live-preview',
    vad: 'default', // default | fast | hybrid
    silenceMs: 300,
    hybridMs: 500,
    tools: 'voice', // voice (prod allowlist) | all | none
    behavior: 'unset', // unset | blocking | nonblocking
    scheduling: 'unset', // unset | INTERRUPT | WHEN_IDLE | SILENT
    thinking: 'unset', // unset | minimal | low ...
    hermes: 'http://127.0.0.1:8690',
    dataset: path.join(REPO, 'hermes/eval/datasets/voice_bench_v1.jsonl'),
    out: path.join(REPO, 'hermes/eval/bench', `${new Date().toISOString().slice(0, 10)}-voice`),
    label: '',
    cases: '',
    repeat: 1,
    saveAudio: '',
    promptSuffix: '',
    engineNote: 'off', // on: feed the [Engine] line before the question, like the browser does
  };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i];
    if (!k.startsWith('--')) continue;
    const key = k.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const v = argv[i + 1];
    i++;
    a[key] = typeof a[key] === 'number' ? Number(v) : v;
  }
  if (!a.label) a.label = `${a.model}-${a.vad}-${a.tools}${a.behavior !== 'unset' ? '-' + a.behavior : ''}`;
  return a;
}

function loadEnvKey() {
  if (process.env.GEMINI_API_KEY) return process.env.GEMINI_API_KEY;
  const envPath = path.join(REPO, 'hermes/.env');
  if (fs.existsSync(envPath)) {
    const m = fs.readFileSync(envPath, 'utf8').match(/^GEMINI_API_KEY=(.*)$/m);
    if (m) return m[1].trim().replace(/^['"]|['"]$/g, '');
  }
  throw new Error('GEMINI_API_KEY not set');
}

// ── audio ────────────────────────────────────────────────────────────────────
function synth(text, voice, cacheDir) {
  fs.mkdirSync(cacheDir, { recursive: true });
  const key = Buffer.from(`${voice}:${text}`).toString('base64url').slice(0, 80);
  const pcmPath = path.join(cacheDir, `${key}.pcm`);
  if (!fs.existsSync(pcmPath)) {
    const aiff = path.join(cacheDir, `${key}.aiff`);
    execFileSync('say', ['-v', voice, '-o', aiff, text]);
    execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', aiff, '-ar', String(IN_RATE), '-ac', '1', '-f', 's16le', pcmPath]);
    fs.rmSync(aiff);
  }
  return fs.readFileSync(pcmPath);
}

/** Byte offset just past the last frame loud enough to count as speech. */
function speechEndOffset(pcm) {
  const frame = (IN_RATE * CHUNK_MS) / 1000; // samples
  const samples = new Int16Array(pcm.buffer, pcm.byteOffset, Math.floor(pcm.length / 2));
  let last = 0;
  for (let s = 0; s < samples.length; s += frame) {
    let sum = 0;
    const end = Math.min(samples.length, s + frame);
    for (let i = s; i < end; i++) sum += (samples[i] / 0x8000) ** 2;
    if (Math.sqrt(sum / (end - s)) > SPEECH_RMS) last = end;
  }
  return last * 2;
}

function wav(pcmChunks, rate) {
  const data = Buffer.concat(pcmChunks);
  const h = Buffer.alloc(44);
  h.write('RIFF', 0);
  h.writeUInt32LE(36 + data.length, 4);
  h.write('WAVEfmt ', 8);
  h.writeUInt32LE(16, 16);
  h.writeUInt16LE(1, 20);
  h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24);
  h.writeUInt32LE(rate * 2, 28);
  h.writeUInt16LE(2, 32);
  h.writeUInt16LE(16, 34);
  h.write('data', 36);
  h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── hermes ───────────────────────────────────────────────────────────────────
// One user per variant on the top tier: the free tier allows 10 voice sessions
// an hour, which a single matrix run exceeds.
const benchHeaders = (args) => ({
  'Content-Type': 'application/json',
  'X-User-Id': `voice-bench-${args.label}`,
  'x-subscription-tier': 'pro',
});

async function hermesJson(url, init) {
  const res = await fetch(url, { ...init, signal: AbortSignal.timeout(90000) });
  const body = await res.json().catch(() => ({}));
  return { status: res.status, body };
}

async function fetchTools(args) {
  if (args.tools === 'none') return [];
  const { body } = await hermesJson(`${args.hermes}/api/coach/tools`);
  let tools = Array.isArray(body.tools) ? body.tools : [];
  if (args.tools === 'voice') tools = tools.filter((t) => PROD_VOICE_TOOLS.has(t.name));
  if (args.behavior !== 'unset') {
    const behavior = args.behavior === 'nonblocking' ? 'NON_BLOCKING' : 'BLOCKING';
    tools = tools.map((t) => ({ ...t, behavior }));
  }
  return tools;
}

async function fetchPrompt(args, c, toolsAvailable) {
  const { status, body } = await hermesJson(`${args.hermes}/api/coach/voice/prompt`, {
    method: 'POST',
    headers: benchHeaders(args),
    body: JSON.stringify({ fen: c.fen, locale: c.locale, tools_available: toolsAvailable }),
  });
  if (status !== 200 || !body.system_prompt) throw new Error(`voice/prompt ${status}`);
  return body.system_prompt + (args.promptSuffix || '');
}

async function runTool(args, fc, sessionId) {
  const { status, body } = await hermesJson(`${args.hermes}/api/coach/tool/${encodeURIComponent(fc.name)}`, {
    method: 'POST',
    headers: benchHeaders(args),
    body: JSON.stringify({ args: fc.args ?? {}, session_id: sessionId }),
  });
  // Same envelope the browser hook sends back to the model.
  if (status !== 200) return { ok: false, response: { error: body?.detail?.message || `Hermes ${status}` } };
  if (body && 'error' in body) return { ok: false, response: { result: body } };
  return { ok: true, response: { result: body.result ?? body } };
}

// ── one case ─────────────────────────────────────────────────────────────────
async function runCase(ai, args, tools, c, pcm) {
  const systemInstruction = await fetchPrompt(args, c, tools.length > 0);
  const config = {
    responseModalities: [Modality.AUDIO],
    systemInstruction,
    inputAudioTranscription: {},
    outputAudioTranscription: {},
  };
  if (tools.length) config.tools = [{ functionDeclarations: tools }];
  if (args.vad === 'fast' || args.vad === 'hybrid') {
    config.realtimeInputConfig = {
      automaticActivityDetection: {
        endOfSpeechSensitivity: 'END_SENSITIVITY_HIGH',
        silenceDurationMs: args.silenceMs,
      },
    };
  }
  if (args.thinking !== 'unset') config.thinkingConfig = { thinkingLevel: args.thinking };

  const rec = {
    id: c.id,
    kind: c.kind,
    locale: c.locale,
    expect_lang: c.expect_lang,
    expect_tools: c.expect_tools,
    label: args.label,
    model: args.model,
    prompt_bytes: Buffer.byteLength(systemInstruction),
    tool_count: tools.length,
    tools: [],
    user_text: '',
    model_text: '',
    usage: { prompt: 0, response: 0, cached: 0 },
    events: [],
    segments: [],
  };
  const outAudio = [];
  let lastAudioAt = 0;
  let segBreak = false;
  let done = false;
  let doneResolve;
  const donePromise = new Promise((r) => (doneResolve = r));
  let tSpeechEnd = null;
  let pendingTools = 0;
  let lastToolSentAt = null;
  let lastTurnCompleteAt = null;
  const rel = (t) => (tSpeechEnd === null ? null : Math.round(t - tSpeechEnd));
  const now = () => performance.now();
  const sessionId = `bench-${c.id}-${Date.now()}`;

  // A tool turn is over only once the model has spoken AFTER the last tool
  // response and then completed: with NON_BLOCKING calls (gemini-3.8-live's
  // default) the filler turn completes first and the answer comes as a new turn.
  let lastPostToolAudioAt = null;
  let graceTimer = null;
  const finish = () => {
    if (done) return;
    done = true;
    clearTimeout(graceTimer);
    doneResolve();
  };
  const finishIfIdle = () => {
    if (pendingTools > 0 || lastTurnCompleteAt === null) return;
    if (lastToolSentAt === null || (lastPostToolAudioAt !== null && lastTurnCompleteAt > lastPostToolAudioAt)) {
      finish();
      return;
    }
    // The tool has answered and a turn has completed, but the model has not
    // spoken since: it may still (the NON_BLOCKING answer comes as a new turn
    // 1–3 s later) or it called the tool at the end and has nothing to add.
    if (lastTurnCompleteAt > lastToolSentAt) {
      clearTimeout(graceTimer);
      const mark = lastTurnCompleteAt;
      graceTimer = setTimeout(() => {
        if (lastTurnCompleteAt === mark && (lastPostToolAudioAt === null || lastPostToolAudioAt < lastToolSentAt)) {
          rec.silent_after_tool = true;
          finish();
        }
      }, POST_TOOL_GRACE_MS);
    }
  };

  let session;
  const onmessage = async (msg) => {
    const t = now();
    if (msg.toolCall) {
      const calls = msg.toolCall.functionCalls ?? [];
      rec.events.push({ at: rel(t), type: 'tool_call', names: calls.map((f) => f.name) });
      segBreak = true;
      if (rec.first_tool_ms === undefined) rec.first_tool_ms = rel(t);
      if (rec.first_audio_ms === undefined) rec.filler_before_tool = false;
      pendingTools += calls.length;
      const responses = await Promise.all(
        calls.map(async (fc) => {
          const t0 = now();
          const r = await runTool(args, fc, sessionId).catch((e) => ({ ok: false, response: { error: String(e) } }));
          rec.tools.push({ name: fc.name, args: fc.args, at_ms: rel(t0), exec_ms: Math.round(now() - t0), ok: r.ok });
          const fr = { id: fc.id, name: fc.name, response: r.response };
          if (args.scheduling !== 'unset') fr.scheduling = args.scheduling;
          return fr;
        }),
      );
      try {
        session.sendToolResponse({ functionResponses: responses });
      } catch (e) {
        rec.events.push({ at: rel(now()), type: 'send_tool_error', error: String(e) });
      }
      pendingTools -= calls.length;
      lastToolSentAt = now();
      rec.last_tool_response_ms = rel(lastToolSentAt);
      rec.post_tool_first_audio_ms = undefined;
      return;
    }
    if (msg.toolCallCancellation) rec.events.push({ at: rel(t), type: 'tool_cancel', ids: msg.toolCallCancellation.ids });
    const u = msg.usageMetadata;
    if (u) {
      rec.usage.prompt += u.promptTokenCount ?? 0;
      rec.usage.response += u.responseTokenCount ?? 0;
      rec.usage.cached += u.cachedContentTokenCount ?? 0;
    }
    if (msg.goAway) rec.events.push({ at: rel(t), type: 'go_away' });
    const sc = msg.serverContent;
    if (!sc) return;
    if (sc.inputTranscription?.text) rec.user_text += sc.inputTranscription.text;
    if (sc.outputTranscription?.text) {
      if (rec.first_text_ms === undefined) rec.first_text_ms = rel(t);
      rec.model_text += sc.outputTranscription.text;
      const cur = rec.segments[rec.segments.length - 1];
      if (cur) cur.text += sc.outputTranscription.text;
    }
    if (sc.interrupted) rec.events.push({ at: rel(t), type: 'interrupted' });
    for (const part of sc.modelTurn?.parts ?? []) {
      const d = part.inlineData;
      if (d?.data && d.mimeType?.includes('audio/pcm')) {
        const buf = Buffer.from(d.data, 'base64');
        outAudio.push(buf);
        if (rec.first_audio_ms === undefined) {
          rec.first_audio_ms = rel(t);
          if (rec.filler_before_tool === undefined) rec.filler_before_tool = true;
        }
        // Audio segments: a new one starts after a turn boundary or a pause, so
        // a filler still streaming when the tool returns is not taken for the answer.
        const seg = rec.segments[rec.segments.length - 1];
        if (!seg || segBreak || t - lastAudioAt > SEGMENT_GAP_MS) {
          rec.segments.push({ start: rel(t), end: rel(t), text: '' });
          segBreak = false;
          if (lastToolSentAt !== null && t > lastToolSentAt) {
            lastPostToolAudioAt = t;
            if (rec.post_tool_first_audio_ms === undefined) {
              rec.post_tool_first_audio_ms = Math.round(t - lastToolSentAt);
              rec.answer_ms = rel(t);
            }
          }
        } else {
          seg.end = rel(t);
          if (lastPostToolAudioAt !== null) lastPostToolAudioAt = t;
        }
        lastAudioAt = t;
      }
    }
    if (sc.turnComplete) {
      lastTurnCompleteAt = t;
      segBreak = true;
      rec.events.push({ at: rel(t), type: 'turn_complete' });
      rec.complete_ms = rel(t);
      finishIfIdle();
    }
  };

  const tc0 = now();
  session = await ai.live.connect({
    model: args.model,
    config,
    callbacks: {
      onmessage: (m) => void onmessage(m),
      onerror: (e) => {
        rec.events.push({ at: rel(now()), type: 'ws_error', error: e?.message });
      },
      onclose: (e) => {
        rec.events.push({ at: rel(now()), type: 'ws_close', code: e?.code, reason: e?.reason });
        if (!done) {
          rec.closed_early = true;
          finish();
        }
      },
    },
  });
  rec.connect_ms = Math.round(now() - tc0);

  // The browser hook anchors the board this way right after connect.
  session.sendClientContent({
    turns: [{ role: 'user', parts: [{ text: `Current position (FEN): ${c.fen}` }] }],
    turnComplete: false,
  });
  if (args.engineNote === 'on') {
    // The browser asks for the line as soon as the board changes, i.e. while the
    // student is still thinking — so it is in context before the question.
    const t0 = now();
    const { status, body } = await hermesJson(`${args.hermes}/api/coach/voice/engine-note`, {
      method: 'POST',
      headers: benchHeaders(args),
      body: JSON.stringify({ fen: c.fen }),
    });
    rec.engine_note_ms = Math.round(now() - t0);
    if (status === 200 && body.note) {
      rec.engine_note = body.note;
      session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: body.note }] }], turnComplete: false });
    }
  }

  // Real-time stream: speech, then mic silence until the turn finishes.
  const bytesPerChunk = (IN_RATE * 2 * CHUNK_MS) / 1000;
  const endByte = speechEndOffset(pcm);
  const silence = Buffer.alloc(bytesPerChunk);
  const tStream = now();
  let sent = 0;
  let streamEnded = false;
  const deadline = tStream + (pcm.length / (IN_RATE * 2)) * 1000 + TURN_TIMEOUT_MS;
  for (let i = 0; !done && now() < deadline; i++) {
    const target = tStream + i * CHUNK_MS;
    const wait = target - now();
    if (wait > 0) await sleep(wait);
    if (done) break;
    let chunk = silence;
    if (sent < pcm.length) {
      chunk = pcm.subarray(sent, sent + bytesPerChunk);
      sent += chunk.length;
      if (tSpeechEnd === null && sent >= endByte) tSpeechEnd = now();
    }
    if (streamEnded) continue;
    if (args.vad === 'hybrid' && tSpeechEnd !== null && now() - tSpeechEnd >= args.hybridMs) {
      // Client-side VAD says the user stopped: tell the server and gate the mic.
      session.sendRealtimeInput({ audioStreamEnd: true });
      rec.events.push({ at: rel(now()), type: 'audio_stream_end' });
      streamEnded = true;
      continue;
    }
    try {
      session.sendRealtimeInput({ audio: { data: chunk.toString('base64'), mimeType: `audio/pcm;rate=${IN_RATE}` } });
    } catch {
      break;
    }
  }
  if (!done) {
    rec.timeout = true;
    await Promise.race([donePromise, sleep(100)]);
  }
  try {
    session.close();
  } catch {
    /* closing */
  }
  rec.audio_out_sec = Number((outAudio.reduce((n, b) => n + b.length, 0) / (OUT_RATE * 2)).toFixed(1));
  // No tool, or the model spoke first and the tool (e.g. arrows) needed no follow-up.
  if (!rec.tools.length || rec.silent_after_tool) rec.answer_ms = rec.first_audio_ms;
  rec.lang = detectLang(rec.model_text);
  if (args.saveAudio) {
    const dir = path.join(args.saveAudio, args.label);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(path.join(dir, `${c.id}.wav`), wav(outAudio, OUT_RATE));
  }
  return rec;
}

function detectLang(text) {
  if (!text.trim()) return 'none';
  const cyr = (text.match(/[а-яё]/gi) || []).length;
  const lat = (text.match(/[a-z]/gi) || []).length;
  // ә ғ қ ұ һ і are Kazakh-only; ө ү ң without them is Kyrgyz (Live once
  // heard spoken Kazakh as Kyrgyz and answered in it).
  const kz = (text.match(/[әғқұһі]/gi) || []).length;
  const turkic = (text.match(/[өүң]/gi) || []).length;
  if (kz >= 2) return 'kz';
  if (turkic >= 2) return 'ky';
  if (cyr > lat) return 'ru';
  if (lat > 0) return 'en';
  return 'other';
}

function pct(xs, p) {
  const v = xs.filter((x) => typeof x === 'number').sort((a, b) => a - b);
  if (!v.length) return null;
  return v[Math.min(v.length - 1, Math.floor((p / 100) * v.length))];
}

function summarize(label, recs) {
  const noTool = recs.filter((r) => !r.tools.length);
  const withTool = recs.filter((r) => r.tools.length);
  const langOk = recs.filter((r) => r.lang === r.expect_lang).length;
  const toolHit = recs.filter((r) => r.expect_tools.length && r.tools.some((t) => r.expect_tools.includes(t.name))).length;
  const toolExpected = recs.filter((r) => r.expect_tools.length).length;
  const fillers = withTool.filter((r) => r.filler_before_tool).length;
  const usage = recs.reduce((a, r) => ({ p: a.p + r.usage.prompt, r: a.r + r.usage.response }), { p: 0, r: 0 });
  return {
    label,
    n: recs.length,
    ttfa_p50: pct(recs.map((r) => r.first_audio_ms), 50),
    ttfa_p90: pct(recs.map((r) => r.first_audio_ms), 90),
    ttfa_notool_p50: pct(noTool.map((r) => r.first_audio_ms), 50),
    first_tool_p50: pct(withTool.map((r) => r.first_tool_ms), 50),
    tool_exec_p50: pct(withTool.flatMap((r) => r.tools.map((t) => t.exec_ms)), 50),
    post_tool_audio_p50: pct(withTool.map((r) => r.post_tool_first_audio_ms), 50),
    answer_tool_p50: pct(withTool.map((r) => r.answer_ms), 50),
    answer_tool_p90: pct(withTool.map((r) => r.answer_ms), 90),
    complete_p50: pct(recs.map((r) => r.complete_ms), 50),
    tool_turns: `${withTool.length}/${recs.length}`,
    expected_tool_used: `${toolHit}/${toolExpected}`,
    filler_before_tool: `${fillers}/${withTool.length}`,
    lang_ok: `${langOk}/${recs.length}`,
    timeouts: recs.filter((r) => r.timeout || r.closed_early).length,
    tokens_in: usage.p,
    tokens_out: usage.r,
    audio_out_sec: Number(recs.reduce((n, r) => n + r.audio_out_sec, 0).toFixed(1)),
  };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const ai = new GoogleGenAI({ apiKey: loadEnvKey(), httpOptions: { apiVersion: 'v1alpha' } });
  let cases = fs
    .readFileSync(args.dataset, 'utf8')
    .split('\n')
    .filter((l) => l.trim())
    .map((l) => JSON.parse(l));
  if (args.cases) {
    const want = new Set(args.cases.split(','));
    cases = cases.filter((c) => want.has(c.id));
  }
  const tools = await fetchTools(args);
  const cacheDir = path.join(os.tmpdir(), 'voice-bench-audio');
  fs.mkdirSync(args.out, { recursive: true });
  const outFile = path.join(args.out, `${args.label}.jsonl`);
  const out = fs.createWriteStream(outFile, { flags: 'a' });
  console.log(`▶ ${args.label}: ${args.model}, vad=${args.vad}, tools=${tools.length}, cases=${cases.length}×${args.repeat}`);
  const recs = [];
  for (let rep = 0; rep < args.repeat; rep++) {
    for (const c of cases) {
      const pcm = synth(c.text, c.voice, cacheDir);
      let rec;
      try {
        rec = await runCase(ai, args, tools, c, pcm);
      } catch (e) {
        rec = { id: c.id, label: args.label, error: String(e?.message || e), tools: [], usage: { prompt: 0, response: 0 }, expect_tools: c.expect_tools };
      }
      rec.rep = rep;
      recs.push(rec);
      out.write(JSON.stringify(rec) + '\n');
      const tl = (rec.tools || []).map((t) => `${t.name}:${t.exec_ms}ms${t.ok ? '' : '✗'}`).join(' ');
      console.log(
        `  ${c.id.padEnd(14)} ttfa=${rec.first_audio_ms ?? '—'} answer=${rec.answer_ms ?? '—'} done=${rec.complete_ms ?? '—'} ` +
          `lang=${rec.lang ?? '?'} ${tl}${rec.error ? ' ERROR ' + rec.error : ''}${rec.timeout ? ' TIMEOUT' : ''}`,
      );
      await sleep(500);
    }
  }
  out.end();
  const summary = summarize(args.label, recs.filter((r) => !r.error));
  fs.appendFileSync(path.join(args.out, 'summary.jsonl'), JSON.stringify({ ...summary, args, at: new Date().toISOString() }) + '\n');
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
