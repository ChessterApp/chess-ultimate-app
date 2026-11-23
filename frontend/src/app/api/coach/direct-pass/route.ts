import { after } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireCoachAccess } from '@/lib/coach-access';
import { resolveUserTier } from '@/lib/subscription-tier';
import { captureServer } from '@/lib/analytics/server';
import { ANALYTICS_EVENTS } from '@/lib/analytics/events';
import { mintDirectPass } from '@/lib/coach/direct-pass';
import { coachLearnFloor } from '@/lib/coach/learn-floor';

export const runtime = 'nodejs';

/**
 * GET /api/coach/direct-pass — the pass for the voice pipeline's direct path (src/lib/coach/direct-pass.ts, 23.11):
 * { direct: { url, token, expiresAt } }, or { direct: null } when the path is not set up here. Checked as every coach
 * proxy checks a message: sign-in, access to the coach, the plan.
 */
export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: 'Unauthorized' }, { status: 401 });
  const denied = await requireCoachAccess(userId);
  if (denied) return denied;
  const [tier, learnFloor] = await Promise.all([resolveUserTier(userId), coachLearnFloor(userId)]);
  return Response.json({ direct: mintDirectPass(userId, tier, Date.now(), learnFloor) }, { headers: { 'Cache-Control': 'no-store' } });
}

/**
 * POST /api/coach/direct-pass — a message sent by the direct path, counted as /api/coach/chat counts its own
 * (tracking plan §4 B: the count, never the content). The page sends it after the answer, off the turn's path.
 */
export async function POST() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: 'Unauthorized' }, { status: 401 });
  const tier = await resolveUserTier(userId);
  after(() => captureServer(userId, ANALYTICS_EVENTS.COACH_MESSAGE_SENT, { surface: 'coach', plan: tier, path: 'direct' }));
  return new Response(null, { status: 204 });
}
