import { describe, expect, it } from 'vitest';

import { parseTutorFrame } from '../tutor-stream';

const PIN = '8/2k5/8/8/2b5/8/2Q4K/8 w - - 0 1';

describe('parseTutorFrame (the lesson tutor stream, 2026-10-20)', () => {
  it('reads a delta and the done frame', () => {
    expect(parseTutorFrame('data: {"delta":"Связка — "}')).toEqual({ delta: 'Связка — ' });
    expect(parseTutorFrame('data: {"done":true}')).toEqual({ done: true });
  });

  it("reads the lesson's diagram with its caption and number", () => {
    const frame = parseTutorFrame(`data: {"diagram":{"fen":"${PIN}","caption":"Связка — это нападение…","n":1,"of":2}}`);
    expect(frame).toEqual({ diagram: { fen: PIN, caption: 'Связка — это нападение…', n: 1, of: 2 } });
  });

  it('drops a diagram without a readable position', () => {
    expect(parseTutorFrame('data: {"diagram":{"fen":"not a fen","caption":"x"}}')).toEqual({});
    expect(parseTutorFrame('data: {"diagram":"8/8/8/8/8/8/8/8 w - - 0 1"}')).toEqual({});
  });

  it('ignores lines that are not data frames and broken JSON', () => {
    expect(parseTutorFrame('event: ping')).toBeNull();
    expect(parseTutorFrame('data: {oops')).toBeNull();
    expect(parseTutorFrame('data: "text"')).toBeNull();
  });

  it('carries an error as text', () => {
    expect(parseTutorFrame('data: {"error":"Tutor error: boom"}')).toEqual({ error: 'Tutor error: boom' });
    expect(parseTutorFrame('data: {"error":{"code":500}}')).toEqual({ error: '[object Object]' });
  });
});
