'use client';

/**
 * Rating sparkline for the Chess Empire personalized homepage.
 *
 * Lightweight SVG — no chart library, no animation. Plots `points` (oldest →
 * newest) as a polyline scaled into a 320×80 viewBox. Reads the brand color
 * via `useBranding()` so the stroke matches the white-label theme. Renders
 * an empty state when there are no points yet.
 */
import { useTranslations } from 'next-intl';
import { useBranding } from '@/contexts/OrganizationContext';
import type { CERatingPoint } from '@/lib/chess-empire-client';

interface RatingTrendProps {
  points: CERatingPoint[];
}

const VIEW_W = 320;
const VIEW_H = 80;
const PAD_X = 4;
const PAD_Y = 8;

function buildPath(points: CERatingPoint[]): string {
  if (points.length === 0) return '';
  const ratings = points.map((p) => p.rating);
  const min = Math.min(...ratings);
  const max = Math.max(...ratings);
  const span = max - min || 1;
  const innerW = VIEW_W - PAD_X * 2;
  const innerH = VIEW_H - PAD_Y * 2;
  if (points.length === 1) {
    const y = PAD_Y + innerH / 2;
    return `M ${PAD_X} ${y} L ${VIEW_W - PAD_X} ${y}`;
  }
  return points
    .map((p, i) => {
      const x = PAD_X + (i / (points.length - 1)) * innerW;
      const y = PAD_Y + innerH - ((p.rating - min) / span) * innerH;
      return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

export default function RatingTrend({ points }: RatingTrendProps) {
  const t = useTranslations('empire');
  const branding = useBranding();
  const stroke = branding.primaryColor || '#1a73e8';

  if (!points || points.length === 0) {
    return (
      <section
        data-testid="empire-rating-trend"
        className="rounded-2xl border bg-white p-6 md:p-8 shadow-sm"
        style={{ borderColor: stroke }}
      >
        <h2 className="text-lg md:text-xl font-semibold mb-3" style={{ color: stroke }}>
          {t('ratingTitle')}
        </h2>
        <p data-testid="empire-rating-empty" className="text-sm text-gray-500">
          {t('ratingEmpty')}
        </p>
      </section>
    );
  }

  const first = points[0].rating;
  const last = points[points.length - 1].rating;
  const delta = last - first;
  const deltaSign = delta > 0 ? '+' : delta < 0 ? '−' : '±';
  const deltaAbs = Math.abs(delta);
  const path = buildPath(points);

  return (
    <section
      data-testid="empire-rating-trend"
      className="rounded-2xl border bg-white p-6 md:p-8 shadow-sm"
      style={{ borderColor: stroke }}
    >
      <div className="flex items-baseline justify-between mb-3">
        <h2 className="text-lg md:text-xl font-semibold" style={{ color: stroke }}>
          {t('ratingTitle')}
        </h2>
        <div className="text-right">
          <div className="text-2xl font-bold" style={{ color: stroke }} data-testid="empire-rating-current">
            {last}
          </div>
          <div
            className="text-xs font-medium"
            data-testid="empire-rating-delta"
            style={{ color: delta > 0 ? '#16a34a' : delta < 0 ? '#dc2626' : '#6b7280' }}
          >
            {deltaSign}
            {deltaAbs} {t('ratingDeltaSuffix')}
          </div>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        className="w-full h-20"
        data-testid="empire-rating-svg"
        role="img"
        aria-label={t('ratingTitle')}
      >
        <path
          d={path}
          fill="none"
          stroke={stroke}
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          data-testid="empire-rating-path"
        />
        {points.map((p, i) => {
          const ratings = points.map((q) => q.rating);
          const min = Math.min(...ratings);
          const max = Math.max(...ratings);
          const span = max - min || 1;
          const innerW = VIEW_W - PAD_X * 2;
          const innerH = VIEW_H - PAD_Y * 2;
          const x =
            points.length === 1
              ? VIEW_W / 2
              : PAD_X + (i / (points.length - 1)) * innerW;
          const y =
            points.length === 1
              ? PAD_Y + innerH / 2
              : PAD_Y + innerH - ((p.rating - min) / span) * innerH;
          return (
            <circle
              key={`${p.date}-${i}`}
              cx={x}
              cy={y}
              r={1.5}
              fill={stroke}
              data-testid="empire-rating-point"
            />
          );
        })}
      </svg>
    </section>
  );
}
