import { proxyToHermes } from '@/lib/coach/hermes-proxy';

/** GET /api/coach/daily-plan — today's cards for the coach's home (Hermes src/daily_plan.py). */
export async function GET() {
  return proxyToHermes(null, '/api/coach/daily-plan', 'GET');
}
