import { NextRequest } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';
import { resolveUserTier } from '@/lib/subscription-tier';
import { contextNoteOf } from '@/lib/coach/click-analysis';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/analysis/stream — SSE analysis proxy to Hermes.
 * Mirrors the Flask /api/chat/analysis/stream contract, streaming Hermes'
 * text/event-stream straight through. Frames: {delta} … {done,
 * conversation_id, tokens_used} … {board_actions} … {error}.
 * Hermes' validation / rate-limit / not-found errors come back as plain JSON
 * with Hermes' status and text, before any frame.
 */
export async function POST(request: NextRequest) {
  const { userId } = await auth();
  if (!userId) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const denied = await requireApiAccess();
  if (denied) return denied;

  let body: {
    fen?: string;
    query?: string;
    conversation_id?: string;
    context_type?: string;
    context_note?: string;
  };
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (!body.fen || typeof body.fen !== 'string') {
    return new Response(JSON.stringify({ error: 'Missing fen' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }
  if (!body.query || typeof body.query !== 'string') {
    return new Response(JSON.stringify({ error: 'Missing query' }), {
      status: 400,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  // Same tier the coach proxies send; without it Hermes rate-limits every
  // analysis as free (28.10).
  const tier = await resolveUserTier(userId);

  // Hermes is asked before the stream opens: its error answer (400 «Query too
  // long», 404, 429 «Rate limit exceeded…») goes back as is. Inside a 200
  // stream it became «Hermes error: 429» in the chat (28.10).
  let hermesResponse: Response;
  try {
    hermesResponse = await fetch(`${HERMES_URL}/api/coach/analysis/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': tier,
      },
      body: JSON.stringify({
        fen: body.fen,
        query: body.query,
        conversation_id: body.conversation_id,
        context_type: body.context_type,
        context_note: contextNoteOf(body.context_note),
      }),
      signal: AbortSignal.timeout(60000),
    });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Unknown error';
    return new Response(JSON.stringify({ error: message }), {
      status: 502,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  if (!hermesResponse.ok) {
    let payload: Record<string, unknown> = { error: `Hermes error: ${hermesResponse.status}` };
    try {
      const data = await hermesResponse.json();
      if (data && typeof data === 'object') {
        payload = { ...data };
        // FastAPI's own errors carry `detail`, not `error`.
        if (typeof payload.error !== 'string' && typeof payload.detail === 'string') {
          payload.error = payload.detail;
        }
        if (typeof payload.error !== 'string') payload.error = `Hermes error: ${hermesResponse.status}`;
      }
    } catch {
      // not JSON: keep the status line
    }
    // Hermes' 404 is «conversation not found»: sent as 410, because the mobile app reads a 404 from this route as
    // «route not deployed» and silently retries on the old Flask one (review 28.10).
    return new Response(JSON.stringify(payload), {
      status: hermesResponse.status === 404 ? 410 : hermesResponse.status,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const encoder = new TextEncoder();
  const upstream = hermesResponse.body;

  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      try {
        if (upstream) {
          const reader = upstream.getReader();
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
        }
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Unknown error';
        sendEvent({ error: message });
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
