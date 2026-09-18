import { NextRequest } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { supabaseAdmin } from '@/lib/supabase-admin';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/**
 * POST /api/tutor/[courseSlug]/[lessonSlug]/chat — SSE proxy to the Hermes
 * lesson tutor. Mirrors /api/coach/chat: Clerk-authed, forwards X-User-Id,
 * streams SSE deltas back to the browser. After the stream completes it
 * persists the updated conversation to Supabase `lesson_chat_history` so the
 * existing GET history endpoint keeps working.
 *
 * Lives under /api/tutor (not /api/learn) because next.config.ts rewrites
 * /api/learn/:path* to the Flask backend with beforeFiles priority, which
 * would shadow this file route in production.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ courseSlug: string; lessonSlug: string }> },
) {
  const { userId } = await auth();
  if (!userId) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401,
      headers: { 'Content-Type': 'application/json' },
    });
  }

  const { courseSlug, lessonSlug } = await params;

  let body: { message?: string };
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
  const userMessage = body.message;

  const locale = request.cookies.get('NEXT_LOCALE')?.value || 'ru';
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  const authHeader = request.headers.get('authorization') || '';

  // Fetch lesson context + existing history from Flask (reuses its slug
  // resolution). Failures degrade gracefully — the tutor still answers, just
  // with less grounding, and persistence is skipped when lesson_id is unknown.
  let lessonId: string | null = null;
  let lessonTitle = '';
  let lessonContent = '';
  let history: ChatMessage[] = [];

  try {
    const [lessonRes, historyRes] = await Promise.all([
      fetch(
        `${apiUrl}/api/learn/${courseSlug}/${lessonSlug}?locale=${locale}`,
        { headers: { Authorization: authHeader } },
      ),
      fetch(
        `${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/chat?locale=${locale}`,
        { headers: { Authorization: authHeader } },
      ),
    ]);

    if (lessonRes.ok) {
      const lesson = await lessonRes.json();
      lessonId = lesson?.id ?? null;
      lessonTitle = lesson?.title ?? '';
      lessonContent = lesson?.content ?? '';
    }
    if (historyRes.ok) {
      const data = await historyRes.json();
      history = Array.isArray(data?.messages) ? data.messages : [];
    }
  } catch (err) {
    console.warn('lesson chat: failed to load lesson context', err);
  }

  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    async start(controller) {
      const sendEvent = (data: Record<string, unknown>) => {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(data)}\n\n`));
      };

      let assistantReply = '';
      let hadError = false;

      try {
        const hermesResponse = await fetch(`${HERMES_URL}/api/lesson/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-User-Id': userId,
          },
          body: JSON.stringify({
            message: userMessage,
            lesson_title: lessonTitle,
            lesson_content: lessonContent,
            history,
            locale,
          }),
          signal: AbortSignal.timeout(60000),
        });

        if (!hermesResponse.ok || !hermesResponse.body) {
          hadError = true;
          sendEvent({ error: `Hermes error: ${hermesResponse.status}` });
          controller.close();
          return;
        }

        const reader = hermesResponse.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const handleLine = (line: string) => {
          if (!line.startsWith('data: ')) return;
          try {
            const data = JSON.parse(line.slice(6));
            if (typeof data.delta === 'string') {
              assistantReply += data.delta;
            }
            if (data.error) {
              hadError = true;
            }
            sendEvent(data);
          } catch {
            // Non-JSON data line, skip
          }
        };

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) handleLine(line);
        }
        if (buffer) handleLine(buffer);
      } catch (err: unknown) {
        hadError = true;
        const message = err instanceof Error ? err.message : 'Unknown error';
        sendEvent({ error: message });
      } finally {
        controller.close();
      }

      // Persist the updated conversation (append user + full assistant reply).
      // Never persist error text, and never let a write failure surface to the
      // client — the stream has already completed.
      if (!hadError && assistantReply && lessonId) {
        const updated: ChatMessage[] = [
          ...history,
          { role: 'user', content: userMessage },
          { role: 'assistant', content: assistantReply },
        ];
        try {
          await supabaseAdmin.from('lesson_chat_history').upsert(
            {
              user_id: userId,
              lesson_id: lessonId,
              messages: updated,
              updated_at: 'now()',
            },
            { onConflict: 'user_id,lesson_id' },
          );
        } catch (err) {
          console.error('lesson chat: failed to persist history', err);
        }
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
