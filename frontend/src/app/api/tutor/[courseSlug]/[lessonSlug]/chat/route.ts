import { NextRequest } from 'next/server';
import { auth } from '@clerk/nextjs/server';

import { supabaseAdmin } from '@/lib/supabase-admin';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

/** Cap the puzzle set we forward so a malicious/oversized client body can't
 * blow up the Hermes prompt. Matches Hermes' own render cap. */
const MAX_PUZZLES = 50;

interface PuzzleContextPuzzle {
  order_index?: number;
  fen?: string;
  solution_move?: string;
  solution_line?: string[];
  hint_text?: string;
  source_name?: string;
  completed?: boolean;
  attempts?: number;
}

interface PuzzleContext {
  mode?: 'multi' | 'single' | 'none';
  current_index?: number;
  total_count?: number;
  current_puzzle?: PuzzleContextPuzzle | null;
  current_board_fen?: string;
  puzzles?: PuzzleContextPuzzle[];
}

/** Whitelist a single puzzle to known fields (strips anything unexpected). */
function sanitizePuzzle(p: unknown): PuzzleContextPuzzle | null {
  if (!p || typeof p !== 'object') return null;
  const src = p as Record<string, unknown>;
  const out: PuzzleContextPuzzle = {};
  if (typeof src.order_index === 'number') out.order_index = src.order_index;
  if (typeof src.fen === 'string') out.fen = src.fen;
  if (typeof src.solution_move === 'string') out.solution_move = src.solution_move;
  if (Array.isArray(src.solution_line)) {
    out.solution_line = src.solution_line.filter((m): m is string => typeof m === 'string');
  }
  if (typeof src.hint_text === 'string') out.hint_text = src.hint_text;
  if (typeof src.source_name === 'string') out.source_name = src.source_name;
  if (typeof src.completed === 'boolean') out.completed = src.completed;
  if (typeof src.attempts === 'number') out.attempts = src.attempts;
  return out;
}

/** Validate + sanitize a client-supplied puzzle_context into a forwardable
 * shape, capping the puzzles array and stripping unknown fields. */
function sanitizePuzzleContext(raw: unknown): PuzzleContext | null {
  if (!raw || typeof raw !== 'object') return null;
  const src = raw as Record<string, unknown>;
  const out: PuzzleContext = {};
  if (src.mode === 'multi' || src.mode === 'single' || src.mode === 'none') {
    out.mode = src.mode;
  }
  if (typeof src.current_index === 'number') out.current_index = src.current_index;
  if (typeof src.total_count === 'number') out.total_count = src.total_count;
  if (typeof src.current_board_fen === 'string') out.current_board_fen = src.current_board_fen;
  if (src.current_puzzle) {
    const cur = sanitizePuzzle(src.current_puzzle);
    if (cur) out.current_puzzle = cur;
  }
  if (Array.isArray(src.puzzles)) {
    out.puzzles = src.puzzles
      .slice(0, MAX_PUZZLES)
      .map(sanitizePuzzle)
      .filter((p): p is PuzzleContextPuzzle => p !== null);
  }
  return out;
}

/** Server-side fallback: build a puzzle_context from Flask when the client did
 * not send one (older clients). Best-effort — returns null on any failure. */
async function fetchPuzzleContextFallback(
  apiUrl: string | undefined,
  courseSlug: string,
  lessonSlug: string,
  locale: string,
  authHeader: string,
): Promise<PuzzleContext | null> {
  if (!apiUrl) return null;
  try {
    const res = await fetch(
      `${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/puzzles?locale=${locale}`,
      { headers: { Authorization: authHeader } },
    );
    if (!res.ok) return null;
    const data = await res.json();
    const puzzles = Array.isArray(data?.puzzles) ? data.puzzles : [];
    if (puzzles.length === 0) return null;

    const currentIndex = typeof data?.current_index === 'number' ? data.current_index : undefined;
    const sanitized = puzzles
      .slice(0, MAX_PUZZLES)
      .map(sanitizePuzzle)
      .filter((p: PuzzleContextPuzzle | null): p is PuzzleContextPuzzle => p !== null);
    const current = currentIndex
      ? sanitized.find((p: PuzzleContextPuzzle) => p.order_index === currentIndex)
      : undefined;

    return {
      mode: 'multi',
      current_index: currentIndex,
      total_count: typeof data?.total_count === 'number' ? data.total_count : sanitized.length,
      current_puzzle: current ?? undefined,
      puzzles: sanitized,
    };
  } catch (err) {
    console.warn('lesson chat: puzzle_context fallback failed', err);
    return null;
  }
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

  let body: { message?: string; puzzle_context?: unknown };
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
  const clientPuzzleContext = sanitizePuzzleContext(body.puzzle_context);

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

  // Prefer the client-supplied puzzle context (has live board state); fall back
  // to a server-side fetch for older clients that don't send one.
  const puzzleContext =
    clientPuzzleContext ??
    (await fetchPuzzleContextFallback(apiUrl, courseSlug, lessonSlug, locale, authHeader));

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
            ...(puzzleContext ? { puzzle_context: puzzleContext } : {}),
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
