/**
 * @vitest-environment node
 *
 * Unit tests for the `squares` set-membership validator added in Phase 4 (the
 * Watchtower W01–W03 nodes). Order-free, case-insensitive exact-set matching.
 */
import { describe, it, expect } from 'vitest';
import { type TaskDefinition, judgeSubmission } from '../assessment';

function squaresTask(squares: string[]): TaskDefinition {
  return {
    id: 't',
    competency_code: 'H_ROOK',
    family: 'W01',
    fen: '4k3/r7/8/8/8/8/8/R1B1K3 w - - 0 1',
    prompt_en: 'p',
    prompt_ru: 'p',
    prompt_kk: 'p',
    solution: { squares },
    validator: 'squares',
    hints: [],
  };
}

describe('judgeSubmission — squares validator', () => {
  it('accepts the exact set regardless of order or case', () => {
    const task = squaresTask(['d4', 'e1']);
    expect(judgeSubmission(task, { squares: ['e1', 'd4'] }).correct).toBe(true);
    expect(judgeSubmission(task, { squares: ['E1', 'D4'] }).correct).toBe(true);
  });

  it('rejects a missing, extra, or wrong square', () => {
    const task = squaresTask(['d4', 'e1']);
    expect(judgeSubmission(task, { squares: ['d4'] }).correct).toBe(false); // missing
    expect(judgeSubmission(task, { squares: ['d4', 'e1', 'a1'] }).correct).toBe(false); // extra
    expect(judgeSubmission(task, { squares: ['d4', 'c3'] }).correct).toBe(false); // wrong
  });

  it('de-duplicates a repeated square before matching', () => {
    const task = squaresTask(['h6']);
    expect(judgeSubmission(task, { squares: ['h6', 'h6'] }).correct).toBe(true);
  });

  it('is malformed when either side is empty / junk', () => {
    expect(judgeSubmission(squaresTask(['a1']), { squares: [] }).reason).toBe('malformed');
    expect(judgeSubmission(squaresTask(['a1']), { squares: ['z9'] }).reason).toBe('malformed');
    expect(judgeSubmission(squaresTask([]), { squares: ['a1'] }).reason).toBe('malformed');
  });
});
