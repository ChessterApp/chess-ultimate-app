import { proxyToHermes } from '@/lib/coach/hermes-proxy';

/** GET /api/coach/voice/mode — the voice a student who has not chosen one gets: `live` or `pipeline`
 *  (Hermes COACH_VOICE_MODE). An older Hermes answers 404 and the page stays on Gemini Live. */
export async function GET() {
  return proxyToHermes(null, '/api/coach/voice/mode', 'GET');
}
