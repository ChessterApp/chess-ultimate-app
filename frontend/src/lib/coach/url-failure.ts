/**
 * What a failed link import says (tester 28.11): the coach server's code (src/tools/game_url.GameUrlError — `variant:`,
 * `unreachable:`, `not_found:`, `rate_limited:` with the site, `not_game`, `no_moves`) read in the student's language.
 * Until then its English words reached the student — «Не удалось загрузить партию по ссылке: Could not reach the site
 * the link points to». An earlier coach server's words are read too, so the order of the two updates does not matter.
 */
export type UrlFailure =
  | { key: 'urlVariant'; variant: string }
  | { key: 'urlUnreachable' | 'urlNotFound' | 'urlRateLimited'; site: string }
  | { key: 'urlNotGame' | 'urlNoMoves' | 'urlFailedPlain' };

/** «Lichess» / «Chess.com» for a link to one of them, else "". */
export function linkSite(url: string | null | undefined): string {
  const host = /^\s*(?:https?:\/\/)?([^/\s?#]+)/i.exec(url ?? '')?.[1]?.toLowerCase() ?? '';
  if (host === 'lichess.org' || host.endsWith('.lichess.org')) return 'Lichess';
  if (host === 'chess.com' || host.endsWith('.chess.com')) return 'Chess.com';
  return '';
}

export function urlFailure(code: string | null | undefined, status: number | null | undefined, url: string): UrlFailure {
  const text = (code ?? '').trim();
  const coded = /^(variant|unreachable|not_found|rate_limited):(.*)$/.exec(text);
  const site = coded?.[2] || linkSite(url);
  const withSite = (key: 'urlUnreachable' | 'urlNotFound' | 'urlRateLimited'): UrlFailure =>
    site ? { key, site } : { key: 'urlFailedPlain' };
  if (coded?.[1] === 'variant' && coded[2]) return { key: 'urlVariant', variant: coded[2] };
  if (coded?.[1] === 'not_found' || /does not know this game|returned no game data/i.test(text)) return withSite('urlNotFound');
  if (coded?.[1] === 'rate_limited' || /rate limit/i.test(text)) return withSite('urlRateLimited');
  if (text === 'not_game' || /does not point to a game|only lichess and chess\.com|empty link/i.test(text)) {
    return { key: 'urlNotGame' };
  }
  if (text === 'no_moves' || /has no moves|could not read the moves/i.test(text)) return { key: 'urlNoMoves' };
  // the coach server's own «the site did not answer» (502) — not the site's proxy failing to reach the coach server
  if (coded?.[1] === 'unreachable' || (status === 502 && /could not reach the site/i.test(text))) {
    return withSite('urlUnreachable');
  }
  return { key: 'urlFailedPlain' };
}
