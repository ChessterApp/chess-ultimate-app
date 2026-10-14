import { describe, it, expect } from 'vitest';
import type { CoachMessage } from '@/types/coach';
import { applyStreamFrame, messageText, type StreamFrame } from '../message-stream';

const empty: CoachMessage = { id: 'a', role: 'assistant', content: '', timestamp: new Date(0) };
const run = (frames: StreamFrame[], from: CoachMessage = empty) => frames.reduce(applyStreamFrame, from);

describe('applyStreamFrame — stages', () => {
  it('a turn without stages streams into content as before', () => {
    const m = run([{ delta: 'Hello' }, { delta: ' there' }]);
    expect(m.content).toBe('Hello there');
    expect(m.quick).toBeUndefined();
    expect(m.stage).toBeUndefined();
  });

  it('quick reaction goes to its own line, the answer to content', () => {
    const quick = run([{ stage: 'quick' }, { delta: 'Good ' }, { delta: 'question!' }]);
    expect(quick).toMatchObject({ stage: 'quick', quick: 'Good question!', content: '' });
    const answered = run([{ delta: '\n\n' }, { stage: 'answer' }, { delta: 'The plan is ' }, { delta: 'f4.' }], quick);
    expect(answered).toMatchObject({ stage: 'answer', quick: 'Good question!', content: 'The plan is f4.' });
    expect(messageText(answered)).toBe('Good question!\n\nThe plan is f4.');
  });

  it('the answer stage without a reaction leaves content untouched', () => {
    const m = run([{ stage: 'answer' }, { delta: 'Answer' }]);
    expect(m).toMatchObject({ stage: 'answer', quick: '', content: 'Answer' });
    expect(messageText(m)).toBe('Answer');
  });

  it('a reaction cut short (no answer stage) still reads as text', () => {
    expect(messageText(run([{ stage: 'quick' }, { delta: 'Hmm…' }]))).toBe('Hmm…');
  });
});

describe('applyStreamFrame — turn data', () => {
  it('keeps typed summaries in order and ignores junk ones', () => {
    const m = run([
      { tool_result: { tool: 'get_puzzle', ok: true, summary: { kind: 'puzzle', puzzle_id: 'p', fen: '8/8/8/8/8/8/8/K6k w - - 0 1' } } },
      { tool_result: { tool: 'x', ok: true, summary: { kind: 'nope' } } },
      { tool_result: { tool: 'y', ok: false } },
      { tool_result: { tool: 'identify_opening', ok: true, summary: { kind: 'opening', name: 'Italian', eco: 'C50' } } },
    ]);
    expect(m.summaries?.map((s) => s.kind)).toEqual(['puzzle', 'opening']);
  });

  it('accumulates board actions across frames; game results and turn id as sent', () => {
    const m = run([
      { board_actions: [{ type: 'set_fen', fen: 'x' }] },
      { board_actions: [{ type: 'flip_board' }] },
      { game_results: [] },
      { done: true, turn_id: 't1' },
    ]);
    expect(m.boardActions?.map((a) => a.type)).toEqual(['set_fen', 'flip_board']);
    expect(m.gameResults).toEqual([]);
    expect(m.turnId).toBe('t1');
  });
});
