import { NextRequest } from 'next/server';
import { auth } from '@clerk/nextjs/server';
import { requireApiAccess } from '@/lib/require-api-access';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

/**
 * POST /api/coach/analysis/stream — SSE analysis proxy to Hermes.
 * Mirrors the Flask /api/chat/analysis/stream contract, streaming Hermes'
 * text/event-stream straight through. Frames: {delta} … {done,
 * conversation_id, tokens_used} … {error}.
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

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      try {
        const hermesResponse = await fetch(`${HERMES_URL}/api/coach/analysis/stream`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Id': userId,
          },
          body: JSON.stringify({
            fen: body.fen,
            query: body.query,
            conversation_id: body.conversation_id,
            context_type: body.context_type,
          }),
          signal: AbortSignal.timeout(60000),
        });

        if (!hermesResponse.ok) {
          sendEvent({ error: `Hermes error: ${hermesResponse.status}` });
          controller.close();
          return;
        }

        if (hermesResponse.body) {
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
