import { describe, it, expect } from 'vitest';
import {
  CONTEXT_BAR_PX,
  MINI_BOARD_PX,
  MOVE_STRIP_PX,
  PEEK_MIN_PX,
  PLAY_COACH_MIN_PX,
  PLAY_COMPOSER_PX,
  PLAY_PEEK_PX,
  PLAY_STUDENT_ROW_PX,
  detentCss,
  detentHeights,
  playStageCss,
  sheetReducer,
  snapDetent,
  type Detent,
} from '../sheet-detent';

const phone = { height: 844, width: 390, bar: CONTEXT_BAR_PX, stageChrome: MOVE_STRIP_PX };

describe('detentHeights', () => {
  it('peek leaves the board the full width on a phone', () => {
    const h = detentHeights(phone);
    // 844 - 48 - 36 - 390: the board is exactly 390 px.
    expect(h.peek).toBe(370);
    expect(phone.height - phone.bar - phone.stageChrome - h.peek).toBe(phone.width);
  });

  it('full keeps a pinned mini-board above the sheet', () => {
    const h = detentHeights(phone);
    expect(phone.height - phone.bar - h.full).toBe(MINI_BOARD_PX);
  });

  it('orders peek ≤ half ≤ full', () => {
    for (const box of [phone, { ...phone, height: 780, width: 360 }, { ...phone, height: 1024, width: 768 }]) {
      const h = detentHeights(box);
      expect(h.peek).toBeLessThanOrEqual(h.half);
      expect(h.half).toBeLessThanOrEqual(h.full);
    }
  });

  it('a portrait tablet keeps a usable peek (the board narrows instead)', () => {
    const h = detentHeights({ ...phone, height: 1024, width: 768 });
    expect(h.peek).toBe(PEEK_MIN_PX);
  });

  it('play rows take room from the board, not from peek', () => {
    const explore = detentHeights(phone);
    const play = detentHeights({ ...phone, stageChrome: 100 });
    expect(play.peek).toBeLessThan(explore.peek);
    expect(play.peek).toBeGreaterThanOrEqual(PEEK_MIN_PX);
  });
});

describe('detentCss', () => {
  it('uses the same constants in container units', () => {
    const css = detentCss(MOVE_STRIP_PX);
    expect(css.full).toBe(`calc(100cqh - var(--coach-bar-h) - ${MINI_BOARD_PX}px)`);
    expect(css.peek).toContain(`${PEEK_MIN_PX}px`);
    expect(css.peek).toContain(`${MOVE_STRIP_PX}px - 100cqw`);
    expect(css.half).toContain('60cqh');
  });
});

/**
 * Evaluates one of our CSS lengths for a shell (no safe areas: the pad is its 8 px floor).
 * `measured` is the shell's `--coach-play-peek`; unset, the fallback applies.
 */
function cssPx(css: string, { height, width }: { height: number; width: number }, measured?: number): number {
  const js = css
    .replace(/var\(--coach-play-peek, (\d+)px\)/g, (_m, fallback) => String(measured ?? fallback))
    .replace(/max\(env\(safe-area-inset-bottom\), 8px\)/g, '8')
    .replace(/var\(--coach-bar-h\)/g, String(CONTEXT_BAR_PX))
    .replace(/100cqh/g, String(height))
    .replace(/100cqw/g, String(width))
    .replace(/(\d)cqh/g, `$1*${height / 100}`)
    .replace(/px/g, '')
    .replace(/calc\(/g, '(')
    .replace(/clamp\(/g, 'clamp(')
    .replace(/\bmin\(/g, 'Math.min(')
    .replace(/\bmax\(/g, 'Math.max(');
  const clamp = (lo: number, v: number, hi: number) => Math.min(hi, Math.max(lo, v));
  return new Function('clamp', `return ${js}`)(clamp) as number;
}

describe('play peek', () => {
  const play = { height: 678, width: 393, bar: CONTEXT_BAR_PX, stageChrome: PLAY_STUDENT_ROW_PX + PLAY_COACH_MIN_PX };
  const pad = 8;

  it('hugs the action bar: far under the 232 floor', () => {
    const h = detentHeights({ ...play, peekPx: PLAY_PEEK_PX + pad });
    expect(h.peek).toBe(93);
    expect(h.peek).toBeLessThan(PEEK_MIN_PX);
    expect(h.half).toBe(Math.round(678 * 0.6));
  });

  it('the JS and CSS twins agree on every detent', () => {
    for (const box of [play, { ...play, height: 560, width: 375 }, { ...play, height: 800, width: 430 }]) {
      for (const peekPx of [PLAY_PEEK_PX, PLAY_PEEK_PX + PLAY_COMPOSER_PX]) {
        const js = detentHeights({ ...box, peekPx: peekPx + pad });
        const css = detentCss(box.stageChrome, peekPx);
        for (const d of ['peek', 'half', 'full'] as const) expect(Math.abs(cssPx(css[d], box) - js[d])).toBeLessThan(1); // JS rounds half
      }
    }
  });

  it('explore, puzzle and moments keep the 232 floor', () => {
    expect(detentCss(MOVE_STRIP_PX).peek).toContain(`${PEEK_MIN_PX}px`);
    expect(detentCss(MOVE_STRIP_PX, PLAY_PEEK_PX).peek).not.toContain(`${PEEK_MIN_PX}px`);
    expect(detentCss(MOVE_STRIP_PX).peek).not.toContain('--coach-play-peek');
  });

  it('the constants match the real sheet: 1 border + 20 grabber + 64 bar; composer 8 + 54 + 12', () => {
    expect(PLAY_PEEK_PX).toBe(1 + 20 + 8 + 56);
    expect(PLAY_COMPOSER_PX).toBe(8 + 54 + 12);
  });

  it('the measured peek wins over the fallback', () => {
    const css = detentCss(play.stageChrome, PLAY_PEEK_PX);
    expect(css.peek).toContain(`var(--coach-play-peek, ${PLAY_PEEK_PX}px)`);
    expect(cssPx(css.peek, play)).toBe(PLAY_PEEK_PX + pad);
    expect(cssPx(css.peek, play, 200)).toBe(200 + pad);
  });
});

describe('playStageCss', () => {
  const stage = (height: number, width: number, peekPx = PLAY_PEEK_PX, measured?: number) => {
    const css = playStageCss(peekPx);
    const board = cssPx(css.board, { height, width }, measured);
    const strip = cssPx(css.moveStrip, { height, width }, measured);
    const coach = height - CONTEXT_BAR_PX - ((measured ?? peekPx) + 8) - PLAY_STUDENT_ROW_PX - board - strip;
    return { board, strip, coach };
  };

  it('a 393×678 phone: a full-width board, the coach row takes the rest', () => {
    expect(stage(678, 393)).toEqual({ board: 393, strip: 0, coach: 112 });
  });

  it('chat on: the composer takes from the board, the coach row keeps its minimum', () => {
    const { board, coach } = stage(678, 393, PLAY_PEEK_PX + PLAY_COMPOSER_PX);
    expect(board).toBe(343);
    expect(coach).toBe(PLAY_COACH_MIN_PX);
  });

  it('the board box shrinks as the measured sheet grows (voice notice, a two-line composer)', () => {
    const chat = PLAY_PEEK_PX + PLAY_COMPOSER_PX;
    const boards = [chat, chat + 32, chat + 24 + 32].map((measured) => stage(678, 393, chat, measured));
    expect(boards.map((b) => b.board)).toEqual([343, 311, 287]);
    // Every px the sheet takes comes off the board; the coach row keeps its minimum.
    for (const b of boards) expect(b.coach).toBe(PLAY_COACH_MIN_PX);
  });

  it('an iPhone SE 375×560: the board shrinks first, the coach row keeps 2 lines', () => {
    const { board, coach } = stage(560, 375);
    expect(board).toBe(299);
    expect(coach).toBe(PLAY_COACH_MIN_PX);
  });

  it('a tall phone 430×800 fills its slack with the move strip', () => {
    expect(stage(800, 430)).toEqual({ board: 430, strip: MOVE_STRIP_PX, coach: 161 });
  });

  it('the move strip is whole or gone, never a sliver', () => {
    for (let h = 678; h < 760; h++) expect([0, MOVE_STRIP_PX]).toContain(stage(h, 393).strip);
  });
});

describe('snapDetent', () => {
  const h: Record<Detent, number> = { peek: 300, half: 500, full: 700 };

  it('a slow release lands on the nearest detent', () => {
    expect(snapDetent(320, 0, h)).toBe('peek');
    expect(snapDetent(430, 100, h)).toBe('half');
    expect(snapDetent(650, -100, h)).toBe('full');
  });

  it('a fling up moves to the next detent above the release point', () => {
    expect(snapDetent(320, -900, h)).toBe('half');
    expect(snapDetent(520, -900, h)).toBe('full');
    expect(snapDetent(700, -900, h)).toBe('full');
  });

  it('a fling down moves to the next detent below the release point', () => {
    expect(snapDetent(680, 900, h)).toBe('half');
    expect(snapDetent(480, 900, h)).toBe('peek');
    expect(snapDetent(250, 900, h)).toBe('peek');
  });

  it('a fling beats proximity', () => {
    // Released just above peek but flung up: half, not back to peek.
    expect(snapDetent(305, -600, h)).toBe('half');
  });
});

describe('sheetReducer', () => {
  it('grabber expands and collapses one detent at a time, within bounds', () => {
    expect(sheetReducer('peek', { type: 'expand' })).toBe('half');
    expect(sheetReducer('half', { type: 'expand' })).toBe('full');
    expect(sheetReducer('full', { type: 'expand' })).toBe('full');
    expect(sheetReducer('full', { type: 'collapse' })).toBe('half');
    expect(sheetReducer('peek', { type: 'collapse' })).toBe('peek');
  });

  it('a grabber tap opens peek to half and closes anything else to peek', () => {
    expect(sheetReducer('peek', { type: 'toggle' })).toBe('half');
    expect(sheetReducer('half', { type: 'toggle' })).toBe('peek');
    expect(sheetReducer('full', { type: 'toggle' })).toBe('peek');
  });

  it('focusing the composer goes full (mini-board); tapping the mini-board returns to peek', () => {
    const full = sheetReducer('peek', { type: 'composer_focus' });
    expect(full).toBe('full');
    expect(sheetReducer(full, { type: 'mini_board_tap' })).toBe('peek');
  });

  it('a mode change brings the board back', () => {
    expect(sheetReducer('full', { type: 'mode_changed' })).toBe('peek');
  });

  it('snap takes the detent as given', () => {
    expect(sheetReducer('peek', { type: 'snap', detent: 'full' })).toBe('full');
  });
});
