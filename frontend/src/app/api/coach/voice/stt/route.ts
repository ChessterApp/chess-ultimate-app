import { auth } from '@clerk/nextjs/server';
import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';

export const runtime = 'nodejs';
export const preferredRegion = 'iad1';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/voice/stt — one utterance of the student turned into text (the voice pipeline, 2026-11-18).
 * Body: the audio the page recorded (WAV, 16 kHz mono); `X-Voice-Locale`: the language to expect.
 * Answers { text, model, ms } — the text is empty when no words were heard.
 *
 * The hearing is Hermes' (src/voice_stt.py: OpenRouter's transcription on the coach's one balance, the key on
 * that server — the site holds none). The page used to stream the microphone to Google with a one-use token
 * minted here; that project ran out of credit on 18.11 and every voice connection was closed.
 */
const MAX_BYTES = 2_500_000;
const TIMEOUT_MS = 25000;

export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: 'Unauthorized' }, { status: 401 });
  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  const audio = await request.arrayBuffer();
  if (!audio.byteLength) return Response.json({ error: 'Missing audio' }, { status: 400 });
  if (audio.byteLength > MAX_BYTES) return Response.json({ error: 'Audio too long' }, { status: 413 });
  const locale = (request.headers.get('x-voice-locale') || '').slice(0, 8);

  let upstream: Response;
  try {
    const tier = await resolveUserTier(userId);
    upstream = await fetch(`${HERMES_URL}/api/coach/voice/stt`, {
      method: 'POST',
      headers: {
        'Content-Type': request.headers.get('content-type') || 'audio/wav',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
        ...(locale ? { 'X-Voice-Locale': locale } : {}),
      },
      body: audio,
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (err) {
    console.warn('[voice/stt] hermes unreachable', err instanceof Error ? err.message : err);
    return Response.json({ error: 'STT unreachable' }, { status: 502 });
  }
  if (!upstream.ok) {
    const detail = await upstream.text().catch(() => '');
    console.warn('[voice/stt] hermes', upstream.status, detail.slice(0, 200));
    // 429 (a rate limit) and 402 (no credit) are told apart from a failure, as the reading's are.
    const code = upstream.status === 429 ? 429 : upstream.status === 402 ? 402 : upstream.status === 413 ? 413 : 502;
    const retryAfter = upstream.headers.get('retry-after');
    return Response.json({ error: `STT failed: ${upstream.status}` }, { status: code, headers: retryAfter ? { 'Retry-After': retryAfter } : undefined });
  }
  const data = (await upstream.json().catch(() => null)) as { text?: unknown; model?: unknown; ms?: unknown } | null;
  return Response.json(
    { text: typeof data?.text === 'string' ? data.text : '', model: data?.model ?? null, ms: data?.ms ?? null },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
