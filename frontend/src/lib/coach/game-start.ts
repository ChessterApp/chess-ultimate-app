/** How long a start that failed on the way waits before it is tried again. */
export const START_RETRY_MS = 700;

/**
 * The game's start, tried once more when it failed on the way — the coach answered 500, or nothing reached it
 * (tester 28.11: «Не удалось начать партию: У тренера что-то пошло не так», and the second press started the game).
 * A refusal is not tried again — the membership, a rate limit, the engine busy, a bad request: the same answer would
 * come. Safe on the server: a new start drops a game nobody has moved in (Hermes game_mode._close_unfinished), so a
 * first start that did get through leaves nothing behind.
 */
export async function startWithRetry<T>(
  start: () => Promise<T>,
  wait: (ms: number) => Promise<void> = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
): Promise<T> {
  try {
    return await start();
  } catch (err: unknown) {
    const failure = (err ?? {}) as { code?: unknown; status?: unknown; message?: unknown };
    const onTheWay = failure.code === 'server' || failure.code === 'unreachable';
    if (!onTheWay || failure.status === 403 || failure.message === 'MEMBERSHIP_RESTRICTED') throw err;
    await wait(START_RETRY_MS);
    return start();
  }
}
