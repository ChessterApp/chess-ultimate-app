import { NextRequest, after } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireCoachAccess } from '@/lib/coach-access';
import { captureServer } from '@/lib/analytics/server';
import { ANALYTICS_EVENTS } from '@/lib/analytics/events';

import { resolveUserTier } from '@/lib/subscription-tier';
import { requestLocale } from '@/i18n/detect';
import { hermesErrorFrame, unreachableFrame } from '@/lib/coach/coach-errors';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

// A whole-game review or a hard position can run past a minute (bench
// 2026-09-27: 6 of 36 turns on Hermes bc3cec8); at 60 s the answer was cut off
// mid-sentence with an error. 120 s is what the explorer proxy already runs with.
export const maxDuration = 120;
const HERMES_TIMEOUT_MS = 115_000;

/**
 * POST /api/coach/chat — SSE proxy to Hermes chess coach backend.
 * Streams text tokens, then sends board_actions as a final SSE event.
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const denied = await requireCoachAccess(userId);
  if (denied) return denied;

  let body: {
    message: string;
    fen?: string;
    session_id?: string;
    context_note?: string;
    board_id?: string;
    review_game_id?: string;
    speech?: boolean;
    view_ply?: number;
    view_line?: string[];
  };
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (!body.message || typeof body.message !== 'string') {
    return new Response(JSON.stringify({ error: 'Missing message' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Cookie → Accept-Language, as the page picks its language (28.10: the cookie alone gave 'ru' to Kazakh browsers).
  const locale = requestLocale(request);
  const tier = await resolveUserTier(userId);

  // Tracking plan §4 B — counts the message, never its content. Runs after the
  // response so the PostHog round trip never delays the stream.
  after(() =>
    captureServer(userId, ANALYTICS_EVENTS.COACH_MESSAGE_SENT, { surface: 'coach', plan: tier }),
  );

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      try {
        const hermesResponse = await fetch(`${HERMES_URL}/api/coach/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Id': userId,
            'x-subscription-tier': tier,
          },
          body: JSON.stringify({
            message: body.message,
            fen: body.fen,
            session_id: body.session_id,
            locale,
            context_note:
              typeof body.context_note === 'string' && body.context_note.trim()
                ? body.context_note
                : undefined,
            // The tab the student is looking at — without it the coach acts on
            // the session's last active board, not the one on screen.
            board_id:
              typeof body.board_id === 'string' && body.board_id ? body.board_id : undefined,
            // The daily plan's «review my last game»: Hermes loads that saved game and reviews it.
            review_game_id:
              typeof body.review_game_id === 'string' && body.review_game_id ? body.review_game_id : undefined,
            // The voice pipeline: the answer is read aloud — short, and the move already said is not restated.
            speech: body.speech === true ? true : undefined,
            // The ply of the game's earlier position on the board (the move panel): the coach answers about it.
            view_ply: typeof body.view_ply === 'number' && Number.isFinite(body.view_ply) ? Math.max(0, Math.floor(body.view_ply)) : undefined,
            // A side line of the game on the board (26.10): its moves from the start.
            view_line: Array.isArray(body.view_line) && body.view_line.length <= 400 && body.view_line.every((m) => typeof m === 'string' && m.length <= 10)
              ? body.view_line : undefined,
          }),
          signal: AbortSignal.timeout(HERMES_TIMEOUT_MS),
        });

        if (!hermesResponse.ok) {
          // Hermes's reason with a code the chat shows in the student's language — a 429 used to reach the
          // bubble as «Hermes error: 429», with no «wait N s» (seam audit 28.10).
          sendEvent({ ...(await hermesErrorFrame(hermesResponse)) });
          return;
        }

        const contentType = hermesResponse.headers.get('content-type') || '';

        // Handle SSE streaming from Hermes
        if (contentType.includes('text/event-stream') && hermesResponse.body) {
          const reader = hermesResponse.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6));
                  // Forward all SSE events (delta, board_actions, done, etc.)
                  sendEvent(data);
                } catch {
                  // Non-JSON data line, skip
                }
              }
            }
          }

          // Process remaining buffer
          if (buffer.startsWith('data: ')) {
            try {
              const data = JSON.parse(buffer.slice(6));
              sendEvent(data);
            } catch {
              // skip
            }
          }
        } else {
          // Handle JSON response (non-streaming)
          const data = await hermesResponse.json();
          if (data.message) {
            sendEvent({ delta: data.message });
          }
          if (data.board_actions && data.board_actions.length > 0) {
            sendEvent({ board_actions: data.board_actions });
          }
          if (data.game_results && data.game_results.length > 0) {
            sendEvent({ game_results: data.game_results });
          }
          sendEvent({ done: true, session_id: data.session_id });
        }
      } catch (err: unknown) {
        sendEvent({ ...unreachableFrame(err) });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    },
  });
}
