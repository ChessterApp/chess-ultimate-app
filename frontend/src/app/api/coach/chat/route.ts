import { NextRequest } from 'next/server';
import { auth } from '@clerk/nextjs/server';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

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

  let body: { message: string; fen?: string; session_id?: string };
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
          },
          body: JSON.stringify({
            message: body.message,
            fen: body.fen,
            session_id: body.session_id,
          }),
          signal: AbortSignal.timeout(60000),
        });

        if (!hermesResponse.ok) {
          sendEvent({ error: `Hermes error: ${hermesResponse.status}` });
          controller.close();
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
          sendEvent({ done: true, session_id: data.session_id });
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
