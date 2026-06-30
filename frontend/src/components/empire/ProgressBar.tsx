/**
 * Curriculum progress bar for the Chess Empire personalized homepage.
 *
 * Shows "Lesson X / Y, Level Z" with a filled bar. Missing data renders as `?`
 * rather than NaN so a half-populated profile doesn't look broken.
 */
import { getTranslations } from 'next-intl/server';

interface ProgressBarProps {
  current: number | null | undefined;
  total: number | null | undefined;
  level?: number | null | undefined;
}

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function pctOf(current: number | null | undefined, total: number | null | undefined): number {
  if (!isNum(current) || !isNum(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((current / total) * 100)));
}

export default async function ProgressBar({ current, total, level }: ProgressBarProps) {
  const t = await getTranslations('empire');
  const pct = pctOf(current, total);
  const currentLabel = isNum(current) ? String(current) : '?';
  const totalLabel = isNum(total) ? String(total) : '?';
  const levelLabel = isNum(level) ? String(level) : '?';

  return (
    <section
      data-testid="empire-progress"
      className="rounded-2xl border bg-white p-6 md:p-8 shadow-sm"
      style={{ borderColor: 'var(--brand-primary, #1a73e8)' }}
    >
      <h2
        className="text-lg md:text-xl font-semibold mb-3"
        style={{ color: 'var(--brand-primary, #0f172a)' }}
      >
        {t('progressTitle')}
      </h2>
      <p data-testid="empire-progress-label" className="text-sm text-gray-700 mb-3">
        {t('progressLabel', { current: currentLabel, total: totalLabel, level: levelLabel })}
      </p>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        data-testid="empire-progress-track"
        className="h-3 w-full rounded-full bg-gray-100 overflow-hidden"
      >
        <div
          data-testid="empire-progress-fill"
          className="h-full rounded-full transition-all"
          style={{
            width: `${pct}%`,
            backgroundColor: 'var(--brand-primary, #1a73e8)',
          }}
        />
      </div>
    </section>
  );
}
