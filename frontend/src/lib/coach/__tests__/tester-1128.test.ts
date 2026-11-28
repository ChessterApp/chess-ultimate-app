/**
 * Tester's report of 28.11, the site's side:
 *   5. a game link the coach's server could not fetch said its English words to the student — the server's code is
 *      said in the student's language, with the way to bring the game anyway (lib/coach/url-failure);
 *   6. «Не удалось начать партию: У тренера что-то пошло не так» once, the second press started the game — a start
 *      that failed on the way is tried once more (lib/coach/game-start).
 */
import { describe, expect, it, vi } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { linkSite, urlFailure } from '@/lib/coach/url-failure';
import { START_RETRY_MS, startWithRetry } from '@/lib/coach/game-start';
import { CoachApiError } from '@/lib/coach/boards-api';

const CHESSCOM = 'https://www.chess.com/game/live/97872578329';

describe('a failed link import, said in the student’s language', () => {
  it('names the site of the link', () => {
    expect(linkSite(CHESSCOM)).toBe('Chess.com');
    expect(linkSite('lichess.org/kAdOQKeh')).toBe('Lichess');
    expect(linkSite('https://example.com/x')).toBe('');
  });

  it('reads the coach server’s codes', () => {
    expect(urlFailure('unreachable:Chess.com', 502, CHESSCOM)).toEqual({ key: 'urlUnreachable', site: 'Chess.com' });
    expect(urlFailure('not_found:Lichess', 400, 'https://lichess.org/x')).toEqual({ key: 'urlNotFound', site: 'Lichess' });
    expect(urlFailure('rate_limited:Chess.com', 400, CHESSCOM)).toEqual({ key: 'urlRateLimited', site: 'Chess.com' });
    expect(urlFailure('not_game', 400, 'https://example.com')).toEqual({ key: 'urlNotGame' });
    expect(urlFailure('no_moves', 400, CHESSCOM)).toEqual({ key: 'urlNoMoves' });
    expect(urlFailure('variant:Chess960', 400, CHESSCOM)).toEqual({ key: 'urlVariant', variant: 'Chess960' });
    // a failure with no site named takes the link's own
    expect(urlFailure('unreachable:', 502, CHESSCOM)).toEqual({ key: 'urlUnreachable', site: 'Chess.com' });
  });

  it('reads an earlier coach server’s English words too, so the order of the updates does not matter', () => {
    expect(urlFailure('Could not reach the site the link points to.', 502, CHESSCOM))
      .toEqual({ key: 'urlUnreachable', site: 'Chess.com' });
    expect(urlFailure('Chess.com does not know this game.', 400, CHESSCOM)).toEqual({ key: 'urlNotFound', site: 'Chess.com' });
    expect(urlFailure('Only Lichess and Chess.com game links are supported.', 400, 'x')).toEqual({ key: 'urlNotGame' });
  });

  it('never blames the site for the site’s own proxy failing to reach the coach', () => {
    expect(urlFailure('fetch failed', 502, CHESSCOM)).toEqual({ key: 'urlFailedPlain' });
    expect(urlFailure(undefined, 500, CHESSCOM)).toEqual({ key: 'urlFailedPlain' });
  });

  it('has its words in every language, with no English left in Russian and Kazakh', () => {
    const keys = ['urlUnreachable', 'urlNotFound', 'urlRateLimited', 'urlNotGame', 'urlNoMoves', 'urlFailedPlain'];
    for (const lang of ['ru', 'en', 'kz']) {
      const coach = JSON.parse(readFileSync(join(__dirname, '../../../../messages', `${lang}.json`), 'utf8')).coach;
      for (const key of keys) expect(coach[key], `${lang}.${key}`).toBeTruthy();
      expect(coach.warmupPausedForGame).toContain('{n}');
    }
    const ru = JSON.parse(readFileSync(join(__dirname, '../../../../messages/ru.json'), 'utf8')).coach;
    expect(ru.urlUnreachable).toContain('PGN');
  });
});

describe('a game start that failed on the way is tried once more', () => {
  const noWait = vi.fn(async () => {});

  it('tries again after a 500 or no answer, once', async () => {
    for (const err of [new CoachApiError(500, 'Internal Server Error'), new CoachApiError(0, 'network', 'unreachable')]) {
      const start = vi.fn().mockRejectedValueOnce(err).mockResolvedValueOnce('game');
      await expect(startWithRetry(start, noWait)).resolves.toBe('game');
      expect(start).toHaveBeenCalledTimes(2);
    }
    expect(noWait).toHaveBeenCalledWith(START_RETRY_MS);
    const twice = vi.fn().mockRejectedValue(new CoachApiError(500, 'boom'));
    await expect(startWithRetry(twice, noWait)).rejects.toThrow('boom');
    expect(twice).toHaveBeenCalledTimes(2);
  });

  it('never repeats a refusal', async () => {
    for (const err of [
      new CoachApiError(403, 'MEMBERSHIP_RESTRICTED', 'server'),
      new CoachApiError(429, 'slow down'),
      new CoachApiError(503, 'The engine is unavailable'),
      new CoachApiError(400, 'color must be white, black or random'),
    ]) {
      const start = vi.fn().mockRejectedValue(err);
      await expect(startWithRetry(start, noWait)).rejects.toBe(err);
      expect(start).toHaveBeenCalledTimes(1);
    }
  });
});
