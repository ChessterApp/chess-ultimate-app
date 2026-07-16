import 'server-only';

/**
 * Fire a broadcast on the private Realtime topic `game:{id}` from a route
 * handler (serverless, no persistent socket) via Supabase's HTTP Broadcast API.
 *
 * The service-role key is used so the send bypasses the `realtime.messages`
 * player-only RLS (that policy guards *client* sends/receives; the server is
 * trusted). Broadcast is transport, not truth — a failure here is logged but
 * never fails the request, since clients re-hydrate from Postgres on connect.
 */

import type { BroadcastEvent } from './types';

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY!;

export async function broadcastGameEvent(
  gameId: string,
  event: BroadcastEvent,
  payload: Record<string, unknown>,
): Promise<void> {
  try {
    const res = await fetch(`${supabaseUrl}/realtime/v1/api/broadcast`, {
      method: 'POST',
      headers: {
        apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        messages: [
          {
            topic: `game:${gameId}`,
            event,
            payload,
            private: true,
          },
        ],
      }),
    });
    if (!res.ok) {
      console.error(
        `[live-game] broadcast ${event} on game:${gameId} failed: ${res.status}`,
      );
    }
  } catch (err) {
    console.error(`[live-game] broadcast ${event} on game:${gameId} threw`, err);
  }
}
