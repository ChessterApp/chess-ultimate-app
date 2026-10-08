/**
 * Moves written the Russian way, turned into SAN (2026-10-08).
 *
 * «1.е4 е5 2.Кф3 Кс6 3.Сс4 Сс5 4.с3 Кф6 5.д4 е:д4» — Cyrillic piece letters (Кр Ф Л С К), Cyrillic
 * look-alike and transliterated files (а б в с ц д е э ф г х), «:» or «х» for a capture, zeros for
 * castling. The board's parser (chess.js) knows SAN only. Hermes has the same conversion in
 * hermes/src/notation.py.
 */
const PIECES: Record<string, string> = { Кр: 'K', Ф: 'Q', Л: 'R', С: 'B', К: 'N' };
const FILES: Record<string, string> = {
  а: 'a', б: 'b', в: 'b', с: 'c', ц: 'c', д: 'd', е: 'e', э: 'e', ф: 'f', г: 'g', х: 'h',
};
const F = 'a-hабвсцдеэфгх';
const TOKEN = new RegExp(
  `^(Кр|[КФЛСKQRBN])?([${F}])?([1-8])?([x:х×])?([${F}])([1-8])(?:=?([ФЛСКQRBN]))?([+#!?]*)$`,
);

const file = (ch: string) => FILES[ch] ?? ch;

function token(tok: string): string {
  const m = TOKEN.exec(tok);
  if (!m) return tok;
  const [, p, ff, fr, x, tf, tr, promo, tail] = m;
  const piece = p ? (PIECES[p] ?? p) : '';
  const pr = promo ? `=${PIECES[promo] ?? promo}` : '';
  return `${piece}${ff ? file(ff) : ''}${fr ?? ''}${x ? 'x' : ''}${file(tf)}${tr}${pr}${tail}`;
}

/** *text* with every move token in SAN; words and anything else left as they are. */
export function russianToSan(text: string): string {
  if (!text) return text;
  const t = text
    .replace(/(^|[^0-9-])0-0-0(?![0-9-])/g, '$1O-O-O')
    .replace(/(^|[^0-9-])0-0(?![0-9-])/g, '$1O-O');
  return t
    .split(/(\s+|(?<=\d\.)|(?<=\.\.\.))/)
    .map((part) => {
      if (!part || /^\s+$/.test(part)) return part ?? '';
      const num = /^(\d+\.(?:\.\.)?)(.*)$/.exec(part);
      if (num) return num[2] ? num[1] + token(num[2]) : part;
      return token(part);
    })
    .join('');
}
