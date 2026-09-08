import { auth } from '@clerk/nextjs/server';
import { GoogleGenAI, Modality } from '@google/genai';

import { resolveUserTier, type SubscriptionTier } from '@/lib/subscription-tier';

// Region pin is load-bearing: Gemini mint calls are geo-blocked outside iad1.
export const runtime = 'nodejs';
export const preferredRegion = 'iad1';

const LIVE_MODEL = 'gemini-3.1-flash-live-preview';

const HERMES_URL = process.env.HERMES_URL || 'http://localhost:8642';

// Voice persona, aligned with the Hermes text coach (profiles/chess-coach/SOUL.md):
// the same Chesster coach — Socratic, ask-before-telling, direct and encouraging —
// expressed for a spoken, real-time conversation.
const COACH_VOICE_PROMPT = `You are Chesster's chess coach, the same coach the player types with — now speaking out loud.
You combine engine-level precision with the teaching instincts of great coaches. Ask before telling: understand
what the player is thinking before handing over answers, and lead them to discover ideas through short questions.
Because this is a live voice conversation, keep your sentences short, natural, and conversational — no markdown,
no bullet points, no long monologues. Talk the way a coach sitting beside the board would. Guide the player through
the current position, react to their ideas, and nudge them toward good plans without just handing over the move.
Be direct and encouraging — believe in them, but don't let them off easy. Praise sound reasoning and gently redirect
mistakes. You can refer to squares, pieces, threats, and simple plans out loud. Never break character or say things
like "as a chess AI". When you are unsure what they see, ask a short question rather than lecturing.`;

// Appended when tools are available, so the voice coach uses them instead of guessing.
const COACH_TOOL_GUIDANCE = `

You have tools. Use board_control to demonstrate ideas directly on the board — set positions, draw arrows,
highlight squares, or step through moves as you explain. Use the engine and database tools (analyze the position,
search master games, opening and position stats) instead of guessing or inventing lines. Call a tool when it
makes your point concrete; keep talking naturally while you do.
IMPORTANT for a live voice conversation: the moment you decide to call a tool, FIRST speak a brief spoken
acknowledgment out loud (something like "let me check that" or "one sec, looking now") and THEN make the tool
call. Never go silent while a tool runs — the player should always hear you respond right away.`;

// Voice-relevant subset of the chess toolset. The full Hermes toolset (~20
// tools) includes import/sync/link/account actions that make no sense in a live
// spoken position review and only bloat the token constraint. Keep voice to the
// "explain the current position / show master play" tools. Edit here to tune.
const VOICE_TOOL_ALLOWLIST = new Set<string>([
  'board_control',
  'analyze_position',
  'get_position_stats',
  'get_opening_stats',
  'search_master_games',
  'get_game_pgn',
  'compare_variations',
  'score_position_themes',
  'check_moves',
]);

// Recap caps: keep the injected memory small so it never dominates the prompt or
// slows the first token. Per-message truncation + message count + total bytes.
const RECAP_MAX_MSGS = 10;
const RECAP_MAX_CHARS_PER_MSG = 200;
const RECAP_MAX_BYTES = 2048;

/**
 * Keep only the voice-relevant tool declarations. Anything without a string
 * `name` in the allowlist is dropped.
 */
function filterVoiceTools(tools: unknown[]): unknown[] {
  return tools.filter((t) => {
    const name = (t as { name?: unknown })?.name;
    return typeof name === 'string' && VOICE_TOOL_ALLOWLIST.has(name);
  });
}

/**
 * Fetch the chess tools' Gemini functionDeclarations from Hermes. Returns [] on
 * any failure — the voice session must never break because tools are down.
 */
async function fetchToolDeclarations(): Promise<unknown[]> {
  try {
    const res = await fetch(`${HERMES_URL}/api/coach/tools`, {
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      console.warn('[live-token] tools fetch returned', res.status);
      return [];
    }
    const data = await res.json();
    const tools = Array.isArray(data?.tools) ? data.tools : [];
    return tools;
  } catch (err) {
    console.warn('[live-token] failed to fetch tool declarations:', err);
    return [];
  }
}

type VoiceContext =
  | { ok: true; systemPrompt: string }
  | { ok: false; rateLimited: true; retryAfter?: number };

/**
 * Fetch the single-source spoken system prompt from Hermes (persona + profile +
 * spoken style, rendered from SOUL.md). This call ALSO enforces the voice
 * token-mint rate limit server-side, so a 429 means "refuse to mint". Returns
 * `null` on any other failure/timeout so the caller falls back to the hardcoded
 * prompt below — voice must never break because Hermes is down.
 */
async function fetchVoiceContext(
  userId: string,
  opts: {
    fen?: string;
    locale?: string;
    toolsAvailable: boolean;
    tier: SubscriptionTier;
  },
): Promise<VoiceContext | null> {
  try {
    const res = await fetch(`${HERMES_URL}/api/coach/voice/prompt`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'x-subscription-tier': opts.tier,
      },
      body: JSON.stringify({
        fen: opts.fen,
        locale: opts.locale,
        tools_available: opts.toolsAvailable,
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (res.status === 429) {
      let retryAfter: number | undefined;
      try {
        const b = await res.json();
        const d = b?.detail ?? b;
        if (typeof d?.retry_after === 'number') retryAfter = d.retry_after;
      } catch {
        /* ignore */
      }
      return { ok: false, rateLimited: true, retryAfter };
    }
    if (!res.ok) {
      console.warn('[live-token] voice/prompt returned', res.status);
      return null;
    }
    const data = await res.json();
    if (typeof data?.system_prompt === 'string' && data.system_prompt) {
      return { ok: true, systemPrompt: data.system_prompt };
    }
    return null;
  } catch (err) {
    console.warn('[live-token] voice/prompt fetch failed:', err);
    return null;
  }
}

interface VoiceQuota {
  remainingSeconds: number | null; // null = unlimited tier
  limitSeconds: number | null;
  unlimited: boolean;
}

/**
 * Fetch the caller's monthly voice-minutes quota from Hermes. Returns `null` on
 * any failure/timeout so the mint path FAILS OPEN — an outage in the quota
 * lookup must never lock a user out of voice.
 */
async function fetchVoiceQuota(
  userId: string,
  tier: SubscriptionTier,
): Promise<VoiceQuota | null> {
  try {
    const url = new URL(`${HERMES_URL}/internal/voice/quota`);
    url.searchParams.set('user_id', userId);
    url.searchParams.set('tier', tier);
    const res = await fetch(url, {
      headers: { 'X-User-Id': userId, 'x-subscription-tier': tier },
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) {
      console.warn('[live-token] voice quota returned', res.status);
      return null;
    }
    const data = await res.json();
    return {
      remainingSeconds:
        typeof data?.remaining_seconds === 'number'
          ? data.remaining_seconds
          : null,
      limitSeconds:
        typeof data?.limit_seconds === 'number' ? data.limit_seconds : null,
      unlimited: !!data?.unlimited,
    };
  } catch (err) {
    console.warn('[live-token] voice quota fetch failed:', err);
    return null;
  }
}

/** First instant of next month, UTC, ISO string — when the monthly quota resets. */
function nextMonthResetAt(now = new Date()): string {
  return new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1, 0, 0, 0, 0),
  ).toISOString();
}

/**
 * Fetch recent session messages from Hermes for the recap block. Returns [] on
 * any failure — a Hermes outage must never break voice.
 */
async function fetchRecapMessages(
  sessionId: string,
  userId: string,
): Promise<Array<{ role?: string; content?: string; source?: string }>> {
  try {
    const res = await fetch(
      `${HERMES_URL}/api/coach/sessions/${encodeURIComponent(sessionId)}/messages?limit=20`,
      {
        headers: { 'X-User-Id': userId },
        signal: AbortSignal.timeout(5000),
      },
    );
    if (!res.ok) {
      console.error('[live-token] recap fetch returned', res.status);
      return [];
    }
    const data = await res.json();
    return Array.isArray(data?.messages) ? data.messages : [];
  } catch (err) {
    console.error('[live-token] failed to fetch conversation recap:', err);
    return [];
  }
}

/**
 * Strip tool-call noise and markdown artifacts from a recap message so the
 * injected memory reads as plain spoken conversation.
 */
function sanitizeRecapContent(raw: string): string {
  return raw
    // Drop fenced code blocks (often tool-call JSON / engine dumps).
    .replace(/```[\s\S]*?```/g, ' ')
    // Drop any tool-call markup tags.
    .replace(/<\/?tool_call[^>]*>/gi, ' ')
    // Strip inline code / stray backticks and markdown emphasis/heading markers.
    .replace(/`+/g, '')
    .replace(/[*_#>]+/g, '')
    // Drop leading list bullets.
    .replace(/^\s*[-•]\s+/gm, '')
    // Collapse all whitespace (incl. newlines) to single spaces.
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Build a conversation recap block from prior session messages so the voice
 * coach continues seamlessly across modalities. Capped for latency: each
 * message truncated to 200 chars, at most 10 messages, total block ≤2KB.
 * Returns '' if there's nothing.
 */
function buildRecap(
  messages: Array<{ role?: string; content?: string; source?: string }>,
): string {
  let lines = messages
    .filter((m) => m && typeof m.content === 'string' && m.content.trim())
    .map((m) => {
      const label = m.role === 'user' ? 'user' : 'coach';
      const tag = m.source === 'voice' ? ' (spoken)' : '';
      const text = sanitizeRecapContent(m.content as string).slice(
        0,
        RECAP_MAX_CHARS_PER_MSG,
      );
      return { line: `[${label}${tag}] ${text}`, empty: text.length === 0 };
    })
    .filter((x) => !x.empty)
    // Keep only the most recent messages.
    .slice(-RECAP_MAX_MSGS)
    .map((x) => x.line);

  if (lines.length === 0) return '';

  const header =
    '\n\nYou are continuing an ongoing coaching conversation. ' +
    'Recent conversation (oldest first):\n';
  const footer =
    '\nContinue seamlessly — do not re-introduce yourself or repeat prior explanations.';
  const block = () => header + lines.join('\n') + footer;

  // Enforce the total byte budget by dropping the oldest lines first.
  while (lines.length > 1 && Buffer.byteLength(block(), 'utf8') > RECAP_MAX_BYTES) {
    lines = lines.slice(1);
  }

  return block();
}

const jsonResponse = (body: unknown, status: number) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

/**
 * POST /api/coach/live-token — mint a short-lived Gemini Live ephemeral token.
 * The model + Live config are locked into the token constraint server-side so the
 * browser never holds the raw API key and cannot change what it connects to.
 */
export async function POST(request: Request) {
  const { userId } = await auth();
  if (!userId) {
    return jsonResponse({ error: 'Unauthorized' }, 401);
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return jsonResponse({ error: 'Live coach not configured' }, 500);
  }

  // No required inputs — tolerate a missing or malformed body.
  let body: { fen?: string; session_id?: string; locale?: string } = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const fen = body.fen && typeof body.fen === 'string' ? body.fen : undefined;
  const locale =
    body.locale && typeof body.locale === 'string' ? body.locale : undefined;
  const sessionId =
    body.session_id && typeof body.session_id === 'string'
      ? body.session_id
      : null;

  // Resolve the caller's tier server-side (shared helper) so every Hermes call
  // below carries the same x-subscription-tier and the quota check uses it.
  const tier = await resolveUserTier(userId);

  // Fetch the single-source spoken prompt (+ enforce the mint rate limit), the
  // conversation recap, the tool declarations, and the voice-minutes quota from
  // Hermes in parallel — all independent 5s-timeout calls, so running them
  // concurrently keeps mint latency flat. Each degrades gracefully: a Hermes
  // outage yields the hardcoded prompt / no recap / no tools / fail-open quota
  // but still mints the session.
  const [voiceContext, recapMessages, rawTools, quota] = await Promise.all([
    fetchVoiceContext(userId, { fen, locale, toolsAvailable: true, tier }),
    sessionId ? fetchRecapMessages(sessionId, userId) : Promise.resolve([]),
    fetchToolDeclarations(),
    fetchVoiceQuota(userId, tier),
  ]);

  // Voice minutes exhausted → refuse to mint. quota === null means the lookup
  // failed; fail open (mint anyway) so an outage never locks users out.
  if (
    quota &&
    !quota.unlimited &&
    quota.remainingSeconds !== null &&
    quota.remainingSeconds <= 0
  ) {
    return jsonResponse(
      {
        error: 'voice_quota_exhausted',
        remainingSeconds: 0,
        limitSeconds: quota.limitSeconds,
        resetAt: nextMonthResetAt(),
      },
      429,
    );
  }

  // Rate limited by Hermes → refuse to mint so sessions can't spawn unboundedly.
  if (voiceContext && voiceContext.ok === false) {
    return jsonResponse(
      {
        error: 'rate_limited',
        message: 'Too many voice sessions started. Please wait a moment and try again.',
        retry_after: voiceContext.retryAfter,
      },
      429,
    );
  }

  // Curate the toolset down to the voice-relevant allowlist before embedding.
  const functionDeclarations = filterVoiceTools(rawTools);

  // Prefer Hermes' single-source prompt (persona + spoken style + profile + FEN
  // + spoken tool directives, all rendered from SOUL.md). Fall back to the
  // hardcoded constants in this file if Hermes was unreachable.
  let systemInstruction: string;
  if (voiceContext && voiceContext.ok) {
    systemInstruction = voiceContext.systemPrompt;
  } else {
    systemInstruction = COACH_VOICE_PROMPT;
    if (fen) {
      systemInstruction += `\nThe current board position (FEN) is: ${fen}. Refer to it when relevant.`;
    }
    if (functionDeclarations.length > 0) {
      systemInstruction += COACH_TOOL_GUIDANCE;
    }
  }

  // Inject the capped conversation recap so the voice coach continues seamlessly.
  systemInstruction += buildRecap(recapMessages);

  const now = Date.now();
  const expireTime = new Date(now + 30 * 60 * 1000).toISOString();
  const newSessionExpireTime = new Date(now + 60 * 1000).toISOString();

  try {
    const ai = new GoogleGenAI({
      apiKey,
      httpOptions: { apiVersion: 'v1alpha' },
    });

    const liveConfig: Record<string, unknown> = {
      responseModalities: [Modality.AUDIO],
      systemInstruction,
      // Ask the server to issue resumption handles so the client can survive a
      // dropped connection (network blip / session time limit) and reconnect.
      sessionResumption: {},
    };
    if (functionDeclarations.length > 0) {
      liveConfig.tools = [{ functionDeclarations }];
    }

    const token = await ai.authTokens.create({
      config: {
        uses: 1,
        expireTime,
        newSessionExpireTime,
        liveConnectConstraints: {
          model: LIVE_MODEL,
          config: liveConfig,
        },
        httpOptions: { apiVersion: 'v1alpha' },
      },
    });

    return jsonResponse(
      {
        token: token.name,
        model: LIVE_MODEL,
        expiresAt: expireTime,
        // Byte size of the assembled system prompt, for client latency telemetry.
        promptBytes: Buffer.byteLength(systemInstruction, 'utf8'),
        // Voice minutes left this month so the UI can display / count down from
        // it. null when the tier is unlimited or the quota lookup failed open.
        remainingSeconds: quota ? quota.remainingSeconds : null,
        limitSeconds: quota ? quota.limitSeconds : null,
      },
      200,
    );
  } catch (err) {
    console.error('[live-token] failed to mint ephemeral token:', err);
    return jsonResponse({ error: 'Failed to start live session' }, 502);
  }
}
