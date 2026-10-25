import { auth } from '@clerk/nextjs/server';
import { requireCoachAccess } from '@/lib/coach-access';

export const runtime = 'nodejs';
export const preferredRegion = 'iad1';

/**
 * POST /api/coach/voice/tts — one chunk of the coach's answer read aloud (the voice pipeline, 2026-10-25).
 * Body: { text, locale? }. Answers raw 16-bit PCM, 24 kHz, mono; the keys never leave the server.
 *
 * Through OpenRouter when OPENROUTER_API_KEY is set, on the coach's one balance with no per-day cap —
 * Google's own API allows a project 100 TTS calls a day on Tier 1, which the stand used up in half an
 * hour (25.10). Russian and English: ElevenLabs Flash, which streams and starts in ~0.6 s on the stand
 * (Gemini through OpenRouter comes whole, after ~3 s). Kazakh: Gemini Flash TTS, the one heard reading it
 * well. Straight to Google otherwise (GEMINI_API_KEY), streamed as the model produces it.
 */
const TTS_MODEL = () => process.env.COACH_TTS_MODEL || 'elevenlabs/eleven-flash-v2.5';
const TTS_VOICE = () => process.env.COACH_TTS_VOICE || '21m00Tcm4TlvDq8ikWAM';   // ElevenLabs «Rachel»
const TTS_MODEL_KK = () => process.env.COACH_TTS_MODEL_KK || 'google/gemini-3.8-flash-tts';
const TTS_VOICE_KK = () => process.env.COACH_TTS_VOICE_KK || 'Kore';
const GOOGLE_TTS_MODEL = () => process.env.COACH_TTS_MODEL_GOOGLE || 'gemini-3.8-flash-tts';
const GOOGLE_TTS_VOICE = () => process.env.COACH_TTS_VOICE_GOOGLE || 'Kore';
const MAX_CHARS = 600;
const TIMEOUT_MS = 20000;

/** 429 (a rate limit) and 402 (no credit) are told apart from a failure: the browser waits the first out
 *  and tells the student about either instead of dropping the sentence. */
function failure(status: number, headers: Headers | undefined): Response {
  const code = status === 429 ? 429 : status === 402 ? 402 : 502;
  const retryAfter = headers?.get?.('retry-after') ?? null;
  return Response.json({ error: `TTS failed: ${status}` }, { status: code, headers: retryAfter ? { 'Retry-After': retryAfter } : undefined });
}

const pcmHeaders = (model: string, rate: string) => ({
  'Content-Type': 'application/octet-stream',
  'Cache-Control': 'no-store',
  'X-Sample-Rate': rate,
  'X-Tts-Model': model,
});

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: 'Unauthorized' }, { status: 401 });
  const denied = await requireCoachAccess(userId);
  if (denied) return denied;
  const openRouterKey = process.env.OPENROUTER_API_KEY;
  const googleKey = process.env.GEMINI_API_KEY;
  if (!openRouterKey && !googleKey) return Response.json({ error: 'Voice not configured' }, { status: 500 });

  let body: { text?: unknown; locale?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const text = typeof body.text === 'string' ? body.text.trim().slice(0, MAX_CHARS) : '';
  if (!text) return Response.json({ error: 'Missing text' }, { status: 400 });
  const locale = body.locale === 'kk' ? 'kk' : 'other';

  return openRouterKey ? viaOpenRouter(openRouterKey, text, locale) : viaGoogle(googleKey!, text);
}

/** OpenRouter's speech endpoint: raw PCM bytes, streamed by the providers that stream (ElevenLabs). */
async function viaOpenRouter(key: string, text: string, locale: 'kk' | 'other'): Promise<Response> {
  const model = locale === 'kk' ? TTS_MODEL_KK() : TTS_MODEL();
  const voice = locale === 'kk' ? TTS_VOICE_KK() : TTS_VOICE();
  const upstream = await fetch('https://openrouter.ai/api/v1/audio/speech', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'https://chesster.io',
      'X-Title': 'Chesster coach',
    },
    body: JSON.stringify({ model, input: text, voice, response_format: 'pcm' }),
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => '');
    console.warn('[voice/tts] openrouter', upstream.status, detail.slice(0, 200));
    return failure(upstream.status, upstream.headers);
  }
  const rate = /rate=(\d+)/.exec(upstream.headers?.get?.('content-type') || '')?.[1] || '24000';
  return new Response(upstream.body, { status: 200, headers: pcmHeaders(model, rate) });
}

/** Google's own API streams the audio in SSE frames of base64; only the bytes go to the browser. */
async function viaGoogle(key: string, text: string): Promise<Response> {
  const model = GOOGLE_TTS_MODEL();
  const upstream = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:streamGenerateContent?alt=sse`,
    {
      method: 'POST',
      headers: { 'x-goog-api-key': key, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text }] }],
        generationConfig: {
          responseModalities: ['AUDIO'],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: GOOGLE_TTS_VOICE() } } },
        },
      }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    },
  );
  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => '');
    console.warn('[voice/tts] google', upstream.status, detail.slice(0, 200));
    return failure(upstream.status, upstream.headers);
  }

  const reader = upstream.body.getReader();
  const decoder = new TextDecoder();
  let buffered = '';
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      for (;;) {
        const { value, done } = await reader.read();
        if (done) {
          controller.close();
          return;
        }
        buffered += decoder.decode(value, { stream: true });
        const lines = buffered.split('\n');
        buffered = lines.pop() ?? '';
        let sent = false;
        for (const line of lines) {
          if (!line.startsWith('data:')) continue;
          try {
            const frame = JSON.parse(line.slice(5));
            const part = frame?.candidates?.[0]?.content?.parts?.[0];
            const b64 = part?.inlineData?.data;
            if (typeof b64 === 'string' && b64) {
              controller.enqueue(new Uint8Array(Buffer.from(b64, 'base64')));
              sent = true;
            }
          } catch {
            /* a partial frame: wait for more */
          }
        }
        if (sent) return;
      }
    },
    cancel() {
      void reader.cancel();
    },
  });
  return new Response(stream, { status: 200, headers: pcmHeaders(model, '24000') });
}
