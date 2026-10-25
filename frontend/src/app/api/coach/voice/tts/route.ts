import { auth } from '@clerk/nextjs/server';
import { requireCoachAccess } from '@/lib/coach-access';

export const runtime = 'nodejs';
export const preferredRegion = 'iad1';

/**
 * POST /api/coach/voice/tts — one sentence of the coach read aloud (the voice pipeline prototype,
 * 2026-10-25). Body: { text, locale? }. Streams raw 16-bit PCM, 24 kHz, mono (Google's l16) as
 * the model produces it, so the first bytes play while the rest is still being synthesised.
 * Clerk-authenticated; the Google key never leaves the server.
 */
const TTS_MODEL = () => process.env.COACH_TTS_MODEL || 'gemini-3.8-flash-tts';
const TTS_VOICE = () => process.env.COACH_TTS_VOICE || 'Kore';
const MAX_CHARS = 600;
const TIMEOUT_MS = 20000;

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: 'Unauthorized' }, { status: 401 });
  const denied = await requireCoachAccess(userId);
  if (denied) return denied;
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) return Response.json({ error: 'Voice not configured' }, { status: 500 });

  let body: { text?: unknown; locale?: unknown } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }
  const text = typeof body.text === 'string' ? body.text.trim().slice(0, MAX_CHARS) : '';
  if (!text) return Response.json({ error: 'Missing text' }, { status: 400 });

  const upstream = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${TTS_MODEL()}:streamGenerateContent?alt=sse`,
    {
      method: 'POST',
      headers: { 'x-goog-api-key': apiKey, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        contents: [{ parts: [{ text }] }],
        generationConfig: {
          responseModalities: ['AUDIO'],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: TTS_VOICE() } } },
        },
      }),
      signal: AbortSignal.timeout(TIMEOUT_MS),
    },
  );
  if (!upstream.ok || !upstream.body) {
    const detail = await upstream.text().catch(() => '');
    console.warn('[voice/tts] upstream', upstream.status, detail.slice(0, 200));
    return Response.json({ error: `TTS failed: ${upstream.status}` }, { status: 502 });
  }

  // The SSE frames carry base64 audio parts; only the bytes go to the browser.
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
  return new Response(stream, {
    status: 200,
    headers: {
      'Content-Type': 'application/octet-stream',
      'Cache-Control': 'no-store',
      'X-Sample-Rate': '24000',
      'X-Tts-Model': TTS_MODEL(),
    },
  });
}
