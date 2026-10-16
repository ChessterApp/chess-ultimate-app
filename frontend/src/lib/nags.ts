/**
 * Numeric Annotation Glyphs (PGN `$n`) supported by the Database editor.
 * Single source of truth for symbols, groups, i18n keys and toggle rules.
 */

export type NagGroup = 'move' | 'position' | 'other';

export interface NagDef {
  code: number;
  symbol: string;
  group: NagGroup;
  /** Key under `debut.nags.*` */
  i18nKey: string;
}

export const NAGS: readonly NagDef[] = [
  { code: 3, symbol: '!!', group: 'move', i18nKey: 'brilliant' },
  { code: 1, symbol: '!', group: 'move', i18nKey: 'good' },
  { code: 5, symbol: '!?', group: 'move', i18nKey: 'interesting' },
  { code: 6, symbol: '?!', group: 'move', i18nKey: 'dubious' },
  { code: 2, symbol: '?', group: 'move', i18nKey: 'mistake' },
  { code: 4, symbol: '??', group: 'move', i18nKey: 'blunder' },
  { code: 7, symbol: '□', group: 'move', i18nKey: 'onlyMove' },
  { code: 18, symbol: '+−', group: 'position', i18nKey: 'whiteDecisive' },
  { code: 16, symbol: '±', group: 'position', i18nKey: 'whiteModerate' },
  { code: 14, symbol: '⩲', group: 'position', i18nKey: 'whiteSlight' },
  { code: 10, symbol: '=', group: 'position', i18nKey: 'equal' },
  { code: 13, symbol: '∞', group: 'position', i18nKey: 'unclear' },
  { code: 15, symbol: '⩱', group: 'position', i18nKey: 'blackSlight' },
  { code: 17, symbol: '∓', group: 'position', i18nKey: 'blackModerate' },
  { code: 19, symbol: '−+', group: 'position', i18nKey: 'blackDecisive' },
  { code: 146, symbol: 'N', group: 'other', i18nKey: 'novelty' },
  { code: 32, symbol: '⟳', group: 'other', i18nKey: 'development' },
  { code: 36, symbol: '↑', group: 'other', i18nKey: 'initiative' },
  { code: 40, symbol: '→', group: 'other', i18nKey: 'attack' },
  { code: 132, symbol: '⇆', group: 'other', i18nKey: 'counterplay' },
  { code: 22, symbol: '⨀', group: 'other', i18nKey: 'zugzwang' },
  { code: 138, symbol: '⊕', group: 'other', i18nKey: 'timeTrouble' },
  { code: 140, symbol: '∆', group: 'other', i18nKey: 'withIdea' },
];

/** Black-side variants share the White-side symbol. */
const BLACK_SIDE: Record<number, number> = { 33: 32, 37: 36, 41: 40, 133: 132, 23: 22, 139: 138 };

const BY_CODE = new Map(NAGS.map(n => [n.code, n]));

export const MOVE_QUALITY_COLORS: Record<number, string | undefined> = {
  3: '#26c2a3',
  1: '#5c9e31',
  5: '#a855f7',
  6: '#e6b800',
  2: '#f08c00',
  4: '#e03131',
};

export function canonicalNag(code: number): number {
  return BLACK_SIDE[code] ?? code;
}

/** Definition for a code (Black-side variants resolve to the shared symbol); undefined if unsupported. */
export function getNag(code: number): NagDef | undefined {
  return BY_CODE.get(canonicalNag(code));
}

export function nagsInGroup(group: NagGroup): NagDef[] {
  return NAGS.filter(n => n.group === group);
}

/**
 * Toggles `code`: removes it if present; otherwise adds it, replacing any
 * existing symbol of the same group for move/position. Unknown codes are kept.
 */
export function toggleNag(nags: readonly number[] | undefined, code: number): number[] {
  const current = nags ?? [];
  const target = canonicalNag(code);
  if (current.some(n => canonicalNag(n) === target)) {
    return current.filter(n => canonicalNag(n) !== target);
  }
  const group = getNag(code)?.group;
  const kept = group && group !== 'other'
    ? current.filter(n => getNag(n)?.group !== group)
    : current;
  return sortNags([...kept, code]);
}

const GROUP_ORDER: Record<NagGroup, number> = { move: 0, position: 1, other: 2 };

/** Orders move → position → other (palette order within a group); unknown codes last, in place. */
export function sortNags(nags: readonly number[]): number[] {
  const rank = (code: number) => {
    const def = getNag(code);
    return def ? GROUP_ORDER[def.group] * 1000 + NAGS.indexOf(def) : 3000;
  };
  return nags
    .map((code, i) => ({ code, i }))
    .sort((a, b) => rank(a.code) - rank(b.code) || a.i - b.i)
    .map(x => x.code);
}

const SUFFIX_CODES: Record<string, number> = { '!!': 3, '!': 1, '!?': 5, '?!': 6, '?': 2, '??': 4 };

/** Splits a trailing `!`/`?` annotation off a SAN token: `Nf3??` → { san: 'Nf3', nag: 4 }. */
export function parseSanSuffix(token: string): { san: string; nag: number | null } {
  const m = /^(.*?)([!?]{1,2})$/.exec(token);
  if (!m || !m[1]) return { san: token, nag: null };
  return { san: m[1], nag: SUFFIX_CODES[m[2]] };
}

/** Move-quality code for a typed `!`/`?` sequence, or null. */
export function suffixToNag(suffix: string): number | null {
  return SUFFIX_CODES[suffix] ?? null;
}

/** The move-quality NAG of a node, if any. */
export function moveQualityNag(nags: readonly number[] | undefined): NagDef | undefined {
  for (const code of nags ?? []) {
    const def = getNag(code);
    if (def?.group === 'move') return def;
  }
  return undefined;
}

/** Board badge colour for a move-quality symbol (□ has no colour of its own). */
export function nagBadgeColor(def: NagDef): string {
  return MOVE_QUALITY_COLORS[def.code] ?? '#495057';
}
