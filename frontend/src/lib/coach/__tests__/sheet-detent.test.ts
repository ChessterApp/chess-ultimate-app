import { describe, it, expect } from 'vitest';
import {
  CONTEXT_BAR_PX,
  MINI_BOARD_PX,
  MOVE_STRIP_PX,
  PEEK_MIN_PX,
  detentCss,
  detentHeights,
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
