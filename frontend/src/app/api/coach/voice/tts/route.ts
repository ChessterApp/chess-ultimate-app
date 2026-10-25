import { auth } from '@clerk/nextjs/server';
import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

export const runtime = 'nodejs';
export const preferredRegion = 'iad1';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/voice/tts — one chunk of the coach's answer read aloud (the voice pipeline, 2026-10-25).
 * Body: { text, locale? }. Answers raw 16-bit PCM, mono, the sample rate in X-Sample-Rate.
 *
 * The reading is Hermes' (src/voice_tts.py: OpenRouter's speech endpoint on the coach's one balance, the
 * key on that server — the site holds none; Asan, 25.10). An older Hermes answers 404: then the chunk
 * goes straight to Google with GEMINI_API_KEY, streamed as the model produces it — a project is allowed
 * 100 such calls a day on Tier 1, which is why the reading moved.
 */
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

  let body: { text?: unknown; locale?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const text = typeof body.text === 'string' ? body.text.trim().slice(0, MAX_CHARS) : '';
  if (!text) return Response.json({ error: 'Missing text' }, { status: 400 });
  const locale = typeof body.locale === 'string' ? body.locale.slice(0, 8) : undefined;

  const viaHermes = await throughHermes(userId, text, locale);
  if (viaHermes) return viaHermes;
  const googleKey = process.env.GEMINI_API_KEY;
  if (!googleKey) return Response.json({ error: 'Voice not configured' }, { status: 500 });
  return viaGoogle(googleKey, text);
}

/** Hermes reads the chunk; null when this Hermes has no such route yet (404) or cannot be reached. */
async function throughHermes(userId: string, text: string, locale: string | undefined): Promise<Response | null> {
  let upstream: Response;
  try {
    const tier = await resolveUserTier(userId);
    upstream = await fetch(`${HERMES_URL}/api/coach/voice/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-User-Id': userId, 'x-subscription-tier': tier },
      body: JSON.stringify({ text, locale }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    console.warn('[voice/tts] hermes unreachable', err instanceof Error ? err.message : err);
    return null;
  }
  if (upstream.status === 404) return null;
  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => '');
    console.warn('[voice/tts] hermes', upstream.status, detail.slice(0, 200));
    return failure(upstream.status, upstream.headers);
  }
  const rate = upstream.headers?.get?.('x-sample-rate') || '24000';
  const model = upstream.headers?.get?.('x-tts-model') || 'hermes';
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
