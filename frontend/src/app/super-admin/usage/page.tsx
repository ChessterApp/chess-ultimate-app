'use client';

import { Fragment, useEffect, useMemo, useState } from 'react';
import {
  USAGE_TIME_ZONE,
  usageCsv,
  type StudentUsage,
  type UsagePeriod,
  type UsageReport,
} from '@/lib/coach-usage';

const PERIOD_LABELS: Record<UsagePeriod, string> = {
  today: 'Сегодня',
  '7d': '7 дней',
  '30d': '30 дней',
  month: 'Этот месяц',
};

function usd(value: number): string {
  if (value === 0) return '$0';
  if (Math.abs(value) < 0.01) return `$${value.toFixed(4)}`;
  if (Math.abs(value) < 1) return `$${value.toFixed(3)}`;
  return `$${value.toFixed(2)}`;
}

function count(value: number): string {
  return new Intl.NumberFormat('ru-RU').format(Math.round(value));
}

function when(iso: string | null): string {
  if (!iso) return '—';
  return new Intl.DateTimeFormat('ru-RU', {
    timeZone: USAGE_TIME_ZONE,
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(iso));
}

function shortDay(day: string): string {
  const [, m, d] = day.split('-');
  return `${Number(d)}.${m}`;
}

export default function CoachUsagePage() {
  const [period, setPeriod] = useState<UsagePeriod>('7d');
  const [report, setReport] = useState<UsageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const res = await fetch(`/api/admin/coach-usage?period=${period}`, { credentials: 'include' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data?.error || `Ошибка ${res.status}`);
        if (!cancelled) setReport(data as UsageReport);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Не удалось загрузить');
          setReport(null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [period]);

  const students = useMemo(() => {
    const list = report?.students ?? [];
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((s) =>
      [s.name, s.email, s.userId, ...s.schools].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [report, query]);

  const downloadCsv = () => {
    if (!report) return;
    const blob = new Blob([usageCsv({ ...report, students })], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chesster-ai-usage-${period}-${report.period.days.at(-1) ?? ''}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const totals = report?.totals;
  const maxStudentCost = Math.max(0, ...(report?.students ?? []).map((s) => s.costUsd));

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Расходы на ИИ-тренера</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Кто из учеников сколько тратит: текстовый чат, голос и прочее (уроки, партии с тренером).
          </p>
        </div>
        <div
          role="tablist"
          aria-label="Период"
          className="inline-flex rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 p-0.5"
        >
          {(Object.keys(PERIOD_LABELS) as UsagePeriod[]).map((p) => (
            <button
              key={p}
              role="tab"
              aria-selected={period === p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${
                period === p
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              }`}
            >
              {PERIOD_LABELS[p]}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <Card label="Всего" value={totals ? usd(totals.costUsd) : '…'} loading={loading} strong />
        <Card
          label="Текстовый чат"
          value={totals ? usd(totals.textCostUsd) : '…'}
          hint={totals ? `${count(totals.questions)} вопросов` : undefined}
          loading={loading}
        />
        <Card
          label="Голос"
          value={totals ? usd(totals.voiceCostUsd) : '…'}
          hint={totals ? `${count(totals.voiceMinutes)} мин · ${count(totals.voiceTurns)} реплик` : undefined}
          loading={loading}
        />
        <Card
          label="Учеников"
          value={totals ? count(totals.students) : '…'}
          hint={totals && totals.students > 0 ? `в среднем ${usd(totals.costUsd / totals.students)}` : undefined}
          loading={loading}
        />
        <Card
          label="Прочее"
          value={totals ? usd(totals.otherCostUsd) : '…'}
          hint="уроки, партии, память"
          loading={loading}
        />
      </div>

      {report && report.byDay.length > 1 && <DayChart report={report} />}

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по имени, email или школе…"
          className="flex-1 min-w-[240px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        />
        <button
          onClick={downloadCsv}
          disabled={!report || students.length === 0}
          className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-800 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          Скачать CSV
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <table className="min-w-full text-sm" data-testid="usage-table">
          <thead className="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <Th>Ученик</Th>
              <Th right>Вопросов</Th>
              <Th right>Голос, мин</Th>
              <Th right>Чат</Th>
              <Th right>Голос</Th>
              <Th right>Прочее</Th>
              <Th right>Всего</Th>
              <Th>Последний раз</Th>
            </tr>
          </thead>
          <tbody>
            {loading && !report && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                  Загрузка…
                </td>
              </tr>
            )}
            {!loading && students.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-gray-500">
                  {query ? 'Никто не подходит под поиск.' : 'За этот период тренером никто не пользовался.'}
                </td>
              </tr>
            )}
            {students.map((s) => (
              <Fragment key={s.userId}>
                <tr
                  onClick={() => setOpen(open === s.userId ? null : s.userId)}
                  className="border-t border-gray-100 dark:border-gray-700/50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/30"
                  aria-expanded={open === s.userId}
                >
                  <Td>
                    <div className="font-medium text-gray-900 dark:text-gray-100">{s.name || s.email || s.userId}</div>
                    <div className="text-xs text-gray-500">
                      {[s.name ? s.email : null, s.schools.join(', ')].filter(Boolean).join(' · ') || '—'}
                    </div>
                  </Td>
                  <Td right>{count(s.questions)}</Td>
                  <Td right>{s.voiceMinutes ? s.voiceMinutes.toFixed(1) : '—'}</Td>
                  <Td right>{usd(s.textCostUsd)}</Td>
                  <Td right>{usd(s.voiceCostUsd)}</Td>
                  <Td right>{usd(s.otherCostUsd)}</Td>
                  <Td right>
                    <div className="flex items-center justify-end gap-2">
                      <span className="hidden 2xl:block h-1.5 w-12 rounded bg-gray-100 dark:bg-gray-700 overflow-hidden">
                        <span
                          className="block h-full bg-blue-500"
                          style={{ width: `${maxStudentCost ? (s.costUsd / maxStudentCost) * 100 : 0}%` }}
                        />
                      </span>
                      <span className="font-semibold">{usd(s.costUsd)}</span>
                    </div>
                  </Td>
                  <Td>{when(s.lastActiveAt)}</Td>
                </tr>
                {open === s.userId && (
                  <tr className="bg-gray-50/70 dark:bg-gray-900/30">
                    <td colSpan={8} className="px-4 py-4">
                      <StudentDetails student={s} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {report && report.byModel.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <div className="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100">По моделям</div>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <Th>Модель</Th>
                <Th right>Вызовов</Th>
                <Th right>Токенов на входе</Th>
                <Th right>Токенов на выходе</Th>
                <Th right>Стоимость</Th>
              </tr>
            </thead>
            <tbody>
              {report.byModel.map((m) => (
                <tr key={m.model} className="border-t border-gray-100 dark:border-gray-700/50">
                  <Td>{m.model}</Td>
                  <Td right>{count(m.calls)}</Td>
                  <Td right>{count(m.promptTokens)}</Td>
                  <Td right>{count(m.completionTokens)}</Td>
                  <Td right>{usd(m.costUsd)}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {report && (
        <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
          Суммы — оценка по ценам моделей из таблицы Hermes (model_prices.py), а не счёт поставщика.
          «Вопросов» — ходы текстового тренера; минуты голоса — из учёта минут (
          {report.notes.voiceMinutesFrom === 'voice_usage' ? 'voice_usage' : 'итоги голосовых сессий'}).
          Дни — по времени Алматы. Служебные вызовы без ученика: {count(report.service.calls)} на{' '}
          {usd(report.service.costUsd)}. Строк учёта: {count(report.notes.rows)}
          {report.notes.truncated ? ' (показаны первые 200 000 — сузьте период)' : ''}.
        </p>
      )}
    </div>
  );
}

function DayChart({ report }: { report: UsageReport }) {
  const max = Math.max(...report.byDay.map((d) => d.textCostUsd + d.voiceCostUsd + d.otherCostUsd), 0);
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">По дням</span>
        <span className="flex gap-3 text-xs text-gray-500">
          <Legend className="bg-blue-500" label="Чат" />
          <Legend className="bg-emerald-500" label="Голос" />
          <Legend className="bg-amber-400" label="Прочее" />
        </span>
      </div>
      <div className="flex items-end gap-1 h-32" data-testid="usage-days">
        {report.byDay.map((d) => {
          const total = d.textCostUsd + d.voiceCostUsd + d.otherCostUsd;
          const h = (v: number) => (max ? `${(v / max) * 100}%` : '0%');
          return (
            <div
              key={d.day}
              className="flex-1 min-w-0 h-full flex flex-col justify-end"
              title={`${d.day}: ${usd(total)}, учеников ${d.students}`}
            >
              <div className="w-full flex flex-col justify-end h-full rounded-t overflow-hidden">
                <div className="bg-amber-400" style={{ height: h(d.otherCostUsd) }} />
                <div className="bg-emerald-500" style={{ height: h(d.voiceCostUsd) }} />
                <div className="bg-blue-500" style={{ height: h(d.textCostUsd) }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="flex gap-1 mt-1">
        {report.byDay.map((d, i) => (
          <div key={d.day} className="flex-1 min-w-0 text-center text-[10px] text-gray-500 truncate">
            {report.byDay.length <= 10 || i % Math.ceil(report.byDay.length / 10) === 0 ? shortDay(d.day) : ''}
          </div>
        ))}
      </div>
    </div>
  );
}

function StudentDetails({ student }: { student: StudentUsage }) {
  const max = Math.max(...student.byDay.map((d) => d.costUsd), 0);
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">По моделям</div>
        <ul className="space-y-1 text-sm">
          {student.byModel.map((m) => (
            <li key={m.model} className="flex justify-between gap-4">
              <span className="text-gray-700 dark:text-gray-300 truncate">{m.model}</span>
              <span className="text-gray-500 whitespace-nowrap">
                {count(m.calls)} выз. · {usd(m.costUsd)}
              </span>
            </li>
          ))}
        </ul>
        <div className="mt-3 text-xs text-gray-500">
          Токены: {count(student.promptTokens)} на входе, {count(student.completionTokens)} на выходе ·{' '}
          {student.voiceTurns ? `${count(student.voiceTurns)} голосовых реплик · ` : ''}
          <span className="font-mono">{student.userId}</span>
        </div>
      </div>
      <div>
        <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-2">По дням</div>
        <div className="flex items-end gap-0.5 h-16">
          {student.byDay.map((d) => (
            <div
              key={d.day}
              className="flex-1 bg-blue-500/80 rounded-t"
              style={{ height: max ? `${Math.max((d.costUsd / max) * 100, d.costUsd ? 4 : 0)}%` : '0%' }}
              title={`${d.day}: ${usd(d.costUsd)}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Card({
  label,
  value,
  hint,
  loading,
  strong,
}: {
  label: string;
  value: string;
  hint?: string;
  loading?: boolean;
  strong?: boolean;
}) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-4 py-3">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div
        className={`mt-1 ${strong ? 'text-2xl' : 'text-xl'} font-bold text-gray-900 dark:text-gray-100 ${
          loading ? 'opacity-50' : ''
        }`}
      >
        {value}
      </div>
      {hint && <div className="text-xs text-gray-500 mt-0.5">{hint}</div>}
    </div>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`inline-block h-2 w-2 rounded-sm ${className}`} />
      {label}
    </span>
  );
}

function Th({ children, right }: { children?: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500 whitespace-nowrap ${
        right ? 'text-right' : 'text-left'
      }`}
    >
      {children}
    </th>
  );
}

function Td({ children, right }: { children?: React.ReactNode; right?: boolean }) {
  return (
    <td className={`px-3 py-3 text-gray-800 dark:text-gray-200 whitespace-nowrap ${right ? 'text-right' : ''}`}>
      {children}
    </td>
  );
}
