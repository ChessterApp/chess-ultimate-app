/**
 * Who spends how much on the AI coach — the numbers behind /super-admin/usage.
 *
 * Hermes writes one `token_usage` row per model call (the reaction and the
 * answer of a chat turn, each voice turn, lessons, game comments, the memory
 * writer…) with an estimated dollar cost from its price table
 * (hermes/src/model_prices.py). Voice minutes come from the quota ledger
 * `voice_usage` (heartbeats of live sessions). This module only aggregates:
 * no I/O, so it is tested on plain rows.
 */

export type UsagePeriod = 'today' | '7d' | '30d' | 'month';

export const USAGE_PERIODS: readonly UsagePeriod[] = ['today', '7d', '30d', 'month'];

/** Days are counted in the school's time zone (Almaty, UTC+5). */
export const USAGE_TIME_ZONE = 'Asia/Almaty';

export interface TokenUsageRow {
  user_id: string | null;
  surface?: string | null;
  model?: string | null;
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  cached_tokens?: number | null;
  estimated_cost_usd?: number | string | null;
  duration_ms?: number | null;
  tool_name?: string | null;
  turn_id?: string | null;
  created_at: string;
}

export interface VoiceUsageRow {
  user_id: string | null;
  seconds?: number | null;
  last_heartbeat_at?: string | null;
  started_at?: string | null;
}

export interface Person {
  name: string | null;
  email: string | null;
  schools: string[];
}

export interface StudentUsage {
  userId: string;
  name: string | null;
  email: string | null;
  schools: string[];
  /** Chat questions (distinct turns of the text coach). */
  questions: number;
  /** Voice turns (distinct voice turns with tokens). */
  voiceTurns: number;
  voiceMinutes: number;
  textCostUsd: number;
  voiceCostUsd: number;
  otherCostUsd: number;
  costUsd: number;
  promptTokens: number;
  completionTokens: number;
  lastActiveAt: string | null;
  byModel: { model: string; calls: number; costUsd: number }[];
  byDay: { day: string; costUsd: number }[];
}

export interface DayUsage {
  day: string;
  textCostUsd: number;
  voiceCostUsd: number;
  otherCostUsd: number;
  students: number;
}

export interface ModelUsage {
  model: string;
  calls: number;
  promptTokens: number;
  completionTokens: number;
  costUsd: number;
}

export interface UsageReport {
  period: { name: UsagePeriod; from: string; to: string; days: string[] };
  totals: {
    costUsd: number;
    textCostUsd: number;
    voiceCostUsd: number;
    otherCostUsd: number;
    students: number;
    questions: number;
    voiceTurns: number;
    voiceMinutes: number;
    promptTokens: number;
    completionTokens: number;
  };
  students: StudentUsage[];
  byDay: DayUsage[];
  byModel: ModelUsage[];
  /** Calls without a student (the playbook, anonymous photo scans, benches). */
  service: { calls: number; costUsd: number };
  notes: { rows: number; truncated: boolean; voiceMinutesFrom: 'voice_usage' | 'token_usage' };
}

const dayFormat = new Intl.DateTimeFormat('en-CA', {
  timeZone: USAGE_TIME_ZONE,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
});

/** "2026-09-30" for an instant, in Almaty time. */
export function dayKey(at: Date | string): string {
  return dayFormat.format(typeof at === 'string' ? new Date(at) : at);
}

/** Almaty's offset from UTC in minutes at *at* (+300 today). */
function zoneOffsetMinutes(at: Date): number {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: USAGE_TIME_ZONE,
    hourCycle: 'h23',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).formatToParts(at);
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  const asUtc = Date.UTC(get('year'), get('month') - 1, get('day'), get('hour'), get('minute'), get('second'));
  return Math.round((asUtc - at.getTime()) / 60000);
}

/** The UTC instant of Almaty midnight starting the day *key* ("YYYY-MM-DD"). */
function startOfDay(key: string, near: Date): Date {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d) - zoneOffsetMinutes(near) * 60000);
}

/** The period's start (inclusive) and the day keys it covers, in Almaty time. */
export function resolvePeriod(name: UsagePeriod, now: Date = new Date()): UsageReport['period'] {
  const today = dayKey(now);
  let fromKey: string;
  if (name === 'today') {
    fromKey = today;
  } else if (name === 'month') {
    fromKey = `${today.slice(0, 8)}01`;
  } else {
    const back = name === '7d' ? 6 : 29;
    fromKey = dayKey(new Date(startOfDay(today, now).getTime() - back * 86400000 + 12 * 3600000));
  }
  const from = startOfDay(fromKey, now);
  const days: string[] = [];
  for (let t = from.getTime() + 12 * 3600000; dayKey(new Date(t)) <= today; t += 86400000) {
    days.push(dayKey(new Date(t)));
  }
  return { name, from: from.toISOString(), to: now.toISOString(), days };
}

/** A Clerk user id — everything else ("system", "anonymous", "bench") is a service call. */
export function isStudentId(id: string | null | undefined): id is string {
  return typeof id === 'string' && id.startsWith('user_');
}

type Kind = 'text' | 'voice' | 'other';

function kindOf(surface: string | null | undefined): Kind {
  if (!surface || surface === 'text') return 'text';
  if (surface === 'voice') return 'voice';
  return 'other';
}

function money(value: number | string | null | undefined): number {
  const n = typeof value === 'string' ? Number(value) : value ?? 0;
  return Number.isFinite(n) ? (n as number) : 0;
}

const round = (n: number, digits = 6) => Math.round(n * 10 ** digits) / 10 ** digits;

interface Acc {
  turns: Set<string>;
  untracked: number;
  voiceTurns: Set<string>;
  voiceMsFromRows: number;
  cost: Record<Kind, number>;
  prompt: number;
  completion: number;
  last: string | null;
  models: Map<string, { calls: number; cost: number }>;
  days: Map<string, number>;
}

function newAcc(): Acc {
  return {
    turns: new Set(),
    untracked: 0,
    voiceTurns: new Set(),
    voiceMsFromRows: 0,
    cost: { text: 0, voice: 0, other: 0 },
    prompt: 0,
    completion: 0,
    last: null,
    models: new Map(),
    days: new Map(),
  };
}

export function aggregateUsage(
  rows: TokenUsageRow[],
  voiceRows: VoiceUsageRow[] | null,
  people: Map<string, Person>,
  period: UsageReport['period'],
  truncated = false,
): UsageReport {
  const accs = new Map<string, Acc>();
  const service = { calls: 0, costUsd: 0 };
  const byDay = new Map<string, DayUsage & { ids: Set<string> }>();
  const byModel = new Map<string, ModelUsage>();
  for (const day of period.days) {
    byDay.set(day, { day, textCostUsd: 0, voiceCostUsd: 0, otherCostUsd: 0, students: 0, ids: new Set() });
  }

  for (const row of rows) {
    const cost = money(row.estimated_cost_usd);
    const model = row.model || 'unknown';
    const prompt = row.prompt_tokens ?? 0;
    const completion = row.completion_tokens ?? 0;
    const m = byModel.get(model) ?? { model, calls: 0, promptTokens: 0, completionTokens: 0, costUsd: 0 };
    m.calls += 1;
    m.promptTokens += prompt;
    m.completionTokens += completion;
    m.costUsd += cost;
    byModel.set(model, m);

    if (!isStudentId(row.user_id)) {
      service.calls += 1;
      service.costUsd += cost;
      continue;
    }
    const kind = kindOf(row.surface);
    const acc = accs.get(row.user_id) ?? newAcc();
    accs.set(row.user_id, acc);
    acc.cost[kind] += cost;
    acc.prompt += prompt;
    acc.completion += completion;
    if (!acc.last || row.created_at > acc.last) acc.last = row.created_at;
    const perModel = acc.models.get(model) ?? { calls: 0, cost: 0 };
    perModel.calls += 1;
    perModel.cost += cost;
    acc.models.set(model, perModel);
    const day = dayKey(row.created_at);
    acc.days.set(day, (acc.days.get(day) ?? 0) + cost);
    const d = byDay.get(day);
    if (d) {
      if (kind === 'text') d.textCostUsd += cost;
      else if (kind === 'voice') d.voiceCostUsd += cost;
      else d.otherCostUsd += cost;
      d.ids.add(row.user_id);
    }
    if (kind === 'text') {
      // The reaction and the answer of one turn share its turn_id.
      if (row.turn_id) acc.turns.add(row.turn_id);
      else if (prompt + completion > 0) acc.untracked += 1;
    } else if (kind === 'voice') {
      if (row.turn_id && prompt + completion > 0) acc.voiceTurns.add(row.turn_id);
      // A session's end row carries its length (0 tokens, no tool).
      if (!row.tool_name && prompt + completion === 0) acc.voiceMsFromRows += row.duration_ms ?? 0;
    }
  }

  const voiceSeconds = new Map<string, number>();
  if (voiceRows) {
    for (const v of voiceRows) {
      if (!isStudentId(v.user_id)) continue;
      voiceSeconds.set(v.user_id, (voiceSeconds.get(v.user_id) ?? 0) + (v.seconds ?? 0));
      const acc = accs.get(v.user_id) ?? newAcc();
      accs.set(v.user_id, acc);
      const at = v.last_heartbeat_at ?? v.started_at ?? null;
      if (at && (!acc.last || at > acc.last)) acc.last = at;
    }
  }

  const students: StudentUsage[] = [...accs.entries()].map(([userId, acc]) => {
    const person = people.get(userId);
    const minutes = voiceRows
      ? (voiceSeconds.get(userId) ?? 0) / 60
      : acc.voiceMsFromRows / 60000;
    const costUsd = acc.cost.text + acc.cost.voice + acc.cost.other;
    return {
      userId,
      name: person?.name ?? null,
      email: person?.email ?? null,
      schools: person?.schools ?? [],
      questions: acc.turns.size + acc.untracked,
      voiceTurns: acc.voiceTurns.size,
      voiceMinutes: round(minutes, 1),
      textCostUsd: round(acc.cost.text),
      voiceCostUsd: round(acc.cost.voice),
      otherCostUsd: round(acc.cost.other),
      costUsd: round(costUsd),
      promptTokens: acc.prompt,
      completionTokens: acc.completion,
      lastActiveAt: acc.last,
      byModel: [...acc.models.entries()]
        .map(([model, v]) => ({ model, calls: v.calls, costUsd: round(v.cost) }))
        .sort((a, b) => b.costUsd - a.costUsd),
      byDay: period.days.map((day) => ({ day, costUsd: round(acc.days.get(day) ?? 0) })),
    };
  });
  students.sort((a, b) => b.costUsd - a.costUsd || b.questions - a.questions);

  const sum = (f: (s: StudentUsage) => number) => students.reduce((t, s) => t + f(s), 0);
  const textCostUsd = sum((s) => s.textCostUsd);
  const voiceCostUsd = sum((s) => s.voiceCostUsd);
  const otherCostUsd = sum((s) => s.otherCostUsd);

  return {
    period,
    totals: {
      costUsd: round(textCostUsd + voiceCostUsd + otherCostUsd),
      textCostUsd: round(textCostUsd),
      voiceCostUsd: round(voiceCostUsd),
      otherCostUsd: round(otherCostUsd),
      students: students.filter((s) => s.costUsd > 0 || s.questions > 0 || s.voiceMinutes > 0).length,
      questions: sum((s) => s.questions),
      voiceTurns: sum((s) => s.voiceTurns),
      voiceMinutes: round(sum((s) => s.voiceMinutes), 1),
      promptTokens: sum((s) => s.promptTokens),
      completionTokens: sum((s) => s.completionTokens),
    },
    students,
    byDay: [...byDay.values()].map(({ ids, ...d }) => ({
      ...d,
      textCostUsd: round(d.textCostUsd),
      voiceCostUsd: round(d.voiceCostUsd),
      otherCostUsd: round(d.otherCostUsd),
      students: ids.size,
    })),
    byModel: [...byModel.values()]
      .map((m) => ({ ...m, costUsd: round(m.costUsd) }))
      .sort((a, b) => b.costUsd - a.costUsd),
    service: { calls: service.calls, costUsd: round(service.costUsd) },
    notes: {
      rows: rows.length,
      truncated,
      voiceMinutesFrom: voiceRows ? 'voice_usage' : 'token_usage',
    },
  };
}

/** The report's students as CSV (UTF-8 with BOM so Excel reads Cyrillic). */
export function usageCsv(report: UsageReport): string {
  const head = [
    'Ученик', 'Email', 'Школа', 'Вопросов в чате', 'Голосовых реплик', 'Минут голоса',
    'Чат, $', 'Голос, $', 'Прочее, $', 'Всего, $', 'Токенов на входе', 'Токенов на выходе',
    'Последняя активность',
  ];
  const cell = (v: string | number | null) => {
    const s = v === null ? '' : String(v);
    return /[",;\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = report.students.map((s) =>
    [
      s.name ?? s.userId, s.email, s.schools.join(', '), s.questions, s.voiceTurns, s.voiceMinutes,
      s.textCostUsd.toFixed(4), s.voiceCostUsd.toFixed(4), s.otherCostUsd.toFixed(4), s.costUsd.toFixed(4),
      s.promptTokens, s.completionTokens, s.lastActiveAt,
    ].map(cell).join(','),
  );
  return '﻿' + [head.map(cell).join(','), ...lines].join('\n') + '\n';
}
