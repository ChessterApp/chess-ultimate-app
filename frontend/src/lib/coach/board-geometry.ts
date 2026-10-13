/** Where a square sits on a board drawn from `orientation`'s side, in % of the board's size. */
export function squareToPercent(
  square: string,
  orientation: 'white' | 'black',
): { left: number; top: number } | null {
  const m = /^([a-h])([1-8])$/.exec(square);
  if (!m) return null;
  const file = m[1].charCodeAt(0) - 97; // a = 0
  const rank = Number(m[2]) - 1; // 1 = 0
  const col = orientation === 'white' ? file : 7 - file;
  const row = orientation === 'white' ? 7 - rank : rank;
  return { left: col * 12.5, top: row * 12.5 };
}
