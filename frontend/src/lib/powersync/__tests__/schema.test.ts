import { describe, it, expect } from 'vitest';
import { AppSchema } from '../schema';

describe('PowerSync AppSchema', () => {
  it('defines all expected tables', () => {
    const tableNames = AppSchema.tables.map((t) => t.name);
    expect(tableNames).toContain('user_games');
    expect(tableNames).toContain('opening_repertoires');
    expect(tableNames).toContain('opening_nodes');
    expect(tableNames).toContain('analysis_conversations');
    expect(tableNames).toContain('user_progress');
    expect(tableNames).toContain('courses');
    expect(tableNames).toContain('lesson_puzzles');
    expect(tableNames).toContain('subscriptions');
    expect(tableNames).toContain('lessons');
    expect(tableNames).toHaveLength(9);
  });

  it('user_games table has correct columns', () => {
    const table = AppSchema.tables.find((t) => t.name === 'user_games')!;
    const colNames = table.columns.map((c) => c.name);

    expect(colNames).toContain('user_id');
    expect(colNames).toContain('white');
    expect(colNames).toContain('black');
    expect(colNames).toContain('pgn');
    expect(colNames).toContain('result');
    expect(colNames).toContain('is_favorite');
    expect(colNames).toContain('tags');
    expect(colNames).toContain('created_at');
  });

  it('repertoire_nodes table has spaced repetition columns', () => {
    const table = AppSchema.tables.find((t) => t.name === 'opening_nodes')!;
    const colNames = table.columns.map((c) => c.name);

    expect(colNames).toContain('ease_factor');
    expect(colNames).toContain('interval_days');
    expect(colNames).toContain('times_trained');
    expect(colNames).toContain('next_review_at');
  });

  it('lessons table has exercise fields', () => {
    const table = AppSchema.tables.find((t) => t.name === 'lessons')!;
    const colNames = table.columns.map((c) => c.name);

    expect(colNames).toContain('exercise_fen');
    expect(colNames).toContain('solution_move');
    expect(colNames).toContain('exercise_type');
    expect(colNames).toContain('hint_text');
  });

  it('schema validates successfully', () => {
    expect(() => AppSchema.validate()).not.toThrow();
  });
});
