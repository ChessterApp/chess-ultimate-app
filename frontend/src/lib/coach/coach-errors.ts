/**
 * Hermes's failures, read once and shown in the student's language. The proxies passed «Hermes error: 429»
 * or «HTTP 500» into the chat, and the game actions dropped Hermes's reason (seam audit 28.10). Server side:
 * `hermesErrorFrame` / `unreachableFrame` build the SSE error frame; client side: `coachErrorText`.
 */

export type CoachErrorCode =
  | 'rate_limited'
  | 'engine_unavailable'
  | 'not_found'
  | 'game_over'
  | 'nothing_to_take_back'
  | 'not_your_move'
  | 'unreachable'
  | 'server'
  | 'unauthorized'
  | 'illegal_move'
  | 'unreadable_move'
  | 'rejected';

export interface CoachErrorFrame {
  error: string;
  error_code: CoachErrorCode;
  rate_limited?: true;
  retry_after?: number;
}

const CODES: ReadonlySet<string> = new Set<CoachErrorCode>([
  'rate_limited', 'engine_unavailable', 'not_found', 'game_over', 'nothing_to_take_back', 'not_your_move',
  'unreachable', 'server', 'unauthorized', 'illegal_move', 'unreadable_move', 'rejected',
]);

/**
 * Hermes's GameError refusals (hermes/src/game_mode.py) by their English text, with the move they name: they reached
 * the ru/kz student as «Ход не принят: e9 is not a legal move here.» (site review 28.10).
 */
const REFUSALS: ReadonlyArray<{ re: RegExp; code: 'illegal_move' | 'unreadable_move' }> = [
  { re: /^(.+?) is not a legal move here\.?$/i, code: 'illegal_move' },
  { re: /^Cannot read the move ['"]?(.*?)['"]?\.?$/i, code: 'unreadable_move' },
  { re: /^Empty move\.?$/i, code: 'unreadable_move' },
];

function refusalOf(text: string | undefined): { code: 'illegal_move' | 'unreadable_move'; move: string } | null {
  const t = (text ?? '').trim();
  for (const r of REFUSALS) {
    const m = r.re.exec(t);
    if (m) return { code: r.code, move: (m[1] ?? '').trim() };
  }
  return null;
}

export function isCoachErrorCode(value: unknown): value is CoachErrorCode {
  return typeof value === 'string' && CODES.has(value);
}

/** Hermes's `detail` text and fields, through the proxy's `{ error, detail }` wrapper if there is one. */
function unwrap(body: unknown): { text: string; retryAfter?: number } {
  let d: unknown = body;
  // proxyToHermes: { error, detail: <Hermes body> }; Hermes: { detail: string | { message, retry_after } }
  for (let i = 0; i < 3 && d && typeof d === 'object' && 'detail' in (d as object); i++) {
    d = (d as { detail: unknown }).detail;
  }
  if (typeof d === 'string') return { text: d };
  if (d && typeof d === 'object') {
    const o = d as Record<string, unknown>;
    const text = (typeof o.message === 'string' && o.message) || (typeof o.error === 'string' && o.error) || '';
    return { text, retryAfter: typeof o.retry_after === 'number' ? o.retry_after : undefined };
  }
  if (body && typeof body === 'object' && typeof (body as { error?: unknown }).error === 'string') {
    return { text: (body as { error: string }).error };
  }
  return { text: '' };
}

/** What a failed Hermes answer (status + JSON body) means for the student. */
export function classifyHermesError(
  status: number,
  body: unknown,
): { code: CoachErrorCode; message: string; retryAfter?: number } {
  const { text, retryAfter } = unwrap(body);
  const message = text || `Hermes error: ${status}`;
  if (status === 429) return { code: 'rate_limited', message, ...(retryAfter !== undefined ? { retryAfter } : {}) };
  // The proxies' own «Unauthorized»: the Clerk session is gone (it reached the student as that word, 28.10).
  if (status === 401) return { code: 'unauthorized', message };
  if (/engine is unavailable/i.test(text) || status === 503) return { code: 'engine_unavailable', message };
  // A 404 is «not found» whatever its body says: a non-JSON Hermes body came through as «Hermes error: 404».
  if (/not found|not a game/i.test(text) || status === 404) return { code: 'not_found', message };
  if (/game is over/i.test(text)) return { code: 'game_over', message };
  if (/nothing to take back/i.test(text)) return { code: 'nothing_to_take_back', message };
  if (/not your move/i.test(text)) return { code: 'not_your_move', message };
  const refusal = refusalOf(text);
  if (refusal) return { code: refusal.code, message };
  // 0: no answer at all; 502/504: the proxy or the gateway could not reach Hermes
  if (status === 0 || status === 502 || status === 504) return { code: 'unreachable', message };
  if (status >= 400 && status < 500 && text) return { code: 'rejected', message };
  return { code: 'server', message };
}

/** A non-ok response read once: its JSON body if it has one, classified. */
export async function classifyResponse(
  res: Pick<Response, 'status'> & { json?: () => Promise<unknown> },
): Promise<{ code: CoachErrorCode; message: string; retryAfter?: number }> {
  let body: unknown = null;
  try {
    body = typeof res.json === 'function' ? await res.json() : null;
  } catch {
    body = null;
  }
  return classifyHermesError(res.status, body);
}

/** The SSE error frame for a non-ok Hermes response (server side, in a proxy). */
export async function hermesErrorFrame(res: Response): Promise<CoachErrorFrame> {
  const c = await classifyResponse(res);
  return {
    error: c.message,
    error_code: c.code,
    ...(c.code === 'rate_limited' ? { rate_limited: true as const } : {}),
    ...(c.retryAfter !== undefined ? { retry_after: c.retryAfter } : {}),
  };
}

/** The SSE error frame for a Hermes the proxy could not reach (network error, timeout). */
export function unreachableFrame(err: unknown): CoachErrorFrame {
  return { error: err instanceof Error ? err.message : 'Hermes unreachable', error_code: 'unreachable' };
}

type Translate = (key: string, values?: Record<string, string | number>) => string;

const KEYS: Record<Exclude<CoachErrorCode, 'rate_limited' | 'rejected' | 'illegal_move' | 'unreadable_move'>, string> = {
  engine_unavailable: 'errorEngineUnavailable',
  not_found: 'errorNotFound',
  game_over: 'errorGameOver',
  nothing_to_take_back: 'errorNothingToTakeBack',
  not_your_move: 'errorNotYourMove',
  unreachable: 'errorCoachUnreachable',
  server: 'errorServer',
  unauthorized: 'errorUnauthorized',
};

/** The student-facing text for a coach failure, in the `coach` namespace's language. */
export function coachErrorText(
  t: Translate,
  code: CoachErrorCode,
  opts: { retryAfter?: number; detail?: string } = {},
): string {
  // Hermes's and the proxies' texts are English: the student gets their own language, the original stays here.
  if (opts.detail) console.warn('[coach] failure shown in the student language, original:', opts.detail);
  if (code === 'rate_limited') {
    const seconds = typeof opts.retryAfter === 'number' && opts.retryAfter > 0 ? Math.ceil(opts.retryAfter) : null;
    return seconds ? t('errorRateLimited', { seconds }) : t('errorRateLimitedNoTime');
  }
  if (code === 'illegal_move' || code === 'unreadable_move' || code === 'rejected') {
    const refusal = refusalOf(opts.detail);
    if (refusal?.code === 'illegal_move' && refusal.move) return t('errorIllegalMove', { move: refusal.move });
    if (refusal?.code === 'unreadable_move') {
      return refusal.move ? t('errorUnreadableMove', { move: refusal.move }) : t('errorEmptyMove');
    }
    // Any other refusal (the proxies' «Missing fen», a side line that does not replay…) was English too.
    return opts.detail || code !== 'rejected' ? t('errorRejected') : t('errorServer');
  }
  return t(KEYS[code]);
}

/**
 * An SSE error frame's text: the proxies tag their own failures with error_code (a 429, Hermes unreachable…) and
 * get worded here; Hermes's in-stream errors carry no code and are already worded for the student.
 */
export function frameErrorText(
  t: Translate,
  data: { error?: unknown; error_code?: unknown; retry_after?: unknown },
): string {
  if (!isCoachErrorCode(data.error_code)) return String(data.error);
  return coachErrorText(t, data.error_code, {
    retryAfter: typeof data.retry_after === 'number' ? data.retry_after : undefined,
    detail: typeof data.error === 'string' ? data.error : undefined,
  });
}
