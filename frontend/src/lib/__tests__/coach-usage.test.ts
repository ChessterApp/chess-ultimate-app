import { describe, it, expect } from 'vitest';
import {
  aggregateUsage,
  dayKey,
  resolvePeriod,
  usageCsv,
  type Person,
  type TokenUsageRow,
} from '../coach-usage';

const NOW = new Date('2026-09-30T10:00:00Z'); // 15:00 in Almaty

describe('resolvePeriod', () => {
  it('counts days in Almaty time', () => {
    expect(dayKey('2026-09-29T19:30:00Z')).toBe('2026-09-30'); // 00:30 in Almaty
    const today = resolvePeriod('today', NOW);
    expect(today.days).toEqual(['2026-09-30']);
    expect(today.from).toBe('2026-09-29T19:00:00.000Z');
  });

  it('covers 7 days, 30 days and the month to date', () => {
    expect(resolvePeriod('7d', NOW).days).toEqual([
      '2026-09-24', '2026-09-25', '2026-09-26', '2026-09-27', '2026-09-28', '2026-09-29', '2026-09-30',
    ]);
    expect(resolvePeriod('30d', NOW).days).toHaveLength(30);
    const month = resolvePeriod('month', NOW);
    expect(month.days[0]).toBe('2026-09-01');
    expect(month.days).toHaveLength(30);
  });
});

const row = (r: Partial<TokenUsageRow>): TokenUsageRow => ({
  user_id: 'user_a',
  surface: 'text',
  model: 'deepseek/deepseek-v4.1-flash',
  prompt_tokens: 100,
  completion_tokens: 20,
  estimated_cost_usd: 0.001,
  created_at: '2026-09-30T05:00:00Z',
  ...r,
});

describe('aggregateUsage', () => {
  const period = resolvePeriod('7d', NOW);
  const people = new Map<string, Person>([
    ['user_a', { name: 'Алия', email: 'aliya@example.com', schools: ['Chess Empire'] }],
  ]);

  it('adds up each student and splits chat, voice and the rest', () => {
    const rows = [
      // one chat turn = the reaction + the answer
      row({ turn_id: 't1', estimated_cost_usd: 0.0001, completion_tokens: 12 }),
      row({ turn_id: 't1', estimated_cost_usd: '0.0012' }),
      row({ turn_id: 't2', estimated_cost_usd: 0.001, created_at: '2026-09-28T05:00:00Z' }),
      // voice: a turn, a tool call (0 tokens) and the session end (0 tokens, duration)
      row({ surface: 'voice', model: 'gemini-3.1-flash-live-preview', turn_id: 'v1', estimated_cost_usd: 0.004 }),
      row({ surface: 'voice', model: 'gemini-live-voice', prompt_tokens: 0, completion_tokens: 0, tool_name: 'get_topic', estimated_cost_usd: 0 }),
      row({ surface: 'voice', model: 'gemini-live-voice', prompt_tokens: 0, completion_tokens: 0, duration_ms: 90_000, estimated_cost_usd: 0 }),
      row({ surface: 'lesson', estimated_cost_usd: 0.002 }),
      row({ user_id: 'user_b', turn_id: 't9', estimated_cost_usd: 0.0005 }),
      // no student: counted apart
      row({ user_id: 'system', surface: 'playbook', estimated_cost_usd: 0.01 }),
      row({ user_id: 'anonymous', surface: 'vision', estimated_cost_usd: 0.02 }),
    ];
    const report = aggregateUsage(rows, null, people, period);
    const [a, b] = report.students;
    expect(a.userId).toBe('user_a');
    expect(a.name).toBe('Алия');
    expect(a.schools).toEqual(['Chess Empire']);
    expect(a.questions).toBe(2);
    expect(a.voiceTurns).toBe(1);
    expect(a.voiceMinutes).toBe(1.5); // from the session-end row: no ledger given
    expect(a.textCostUsd).toBeCloseTo(0.0023, 6);
    expect(a.voiceCostUsd).toBeCloseTo(0.004, 6);
    expect(a.otherCostUsd).toBeCloseTo(0.002, 6);
    expect(a.costUsd).toBeCloseTo(0.0083, 6);
    expect(a.byDay.find((d) => d.day === '2026-09-28')?.costUsd).toBeCloseTo(0.001, 6);
    expect(b.userId).toBe('user_b');
    expect(b.name).toBeNull();
    expect(report.totals.students).toBe(2);
    expect(report.totals.costUsd).toBeCloseTo(0.0088, 6);
    expect(report.service).toEqual({ calls: 2, costUsd: 0.03 });
    expect(report.byModel[0].model).toBe('deepseek/deepseek-v4.1-flash');
    const today = report.byDay.find((d) => d.day === '2026-09-30')!;
    expect(today.students).toBe(2);
    expect(today.voiceCostUsd).toBeCloseTo(0.004, 6);
  });

  it('takes voice minutes from the quota ledger when it is there', () => {
    const report = aggregateUsage(
      [row({ turn_id: 't1' })],
      [
        { user_id: 'user_a', seconds: 120, last_heartbeat_at: '2026-09-30T06:00:00Z' },
        { user_id: 'user_c', seconds: 30, last_heartbeat_at: '2026-09-29T06:00:00Z' },
        { user_id: 'bench', seconds: 999 },
      ],
      people,
      period,
    );
    const a = report.students.find((s) => s.userId === 'user_a')!;
    expect(a.voiceMinutes).toBe(2);
    expect(a.lastActiveAt).toBe('2026-09-30T06:00:00Z');
    // A student who only talked to the voice coach is listed too.
    expect(report.students.find((s) => s.userId === 'user_c')?.voiceMinutes).toBe(0.5);
    expect(report.totals.voiceMinutes).toBe(2.5);
    expect(report.notes.voiceMinutesFrom).toBe('voice_usage');
  });

  it('works on the oldest schema (no surface, no turn ids)', () => {
    const report = aggregateUsage(
      [{ user_id: 'user_a', model: 'm', prompt_tokens: 10, completion_tokens: 5, estimated_cost_usd: 0.5, created_at: '2026-09-30T01:00:00Z' }],
      null,
      new Map(),
      period,
    );
    expect(report.students[0].questions).toBe(1);
    expect(report.students[0].textCostUsd).toBe(0.5);
  });

  it('exports CSV that Excel opens with Cyrillic intact', () => {
    const report = aggregateUsage([row({ turn_id: 't1' })], null, people, period);
    const csv = usageCsv(report);
    expect(csv.startsWith('﻿Ученик,Email,Школа')).toBe(true);
    expect(csv).toContain('Алия,aliya@example.com,Chess Empire,1,0,0,0.0010,');
  });
});
