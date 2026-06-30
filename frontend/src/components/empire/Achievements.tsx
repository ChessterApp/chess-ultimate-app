/**
 * Achievements grid for the Chess Empire personalized homepage.
 *
 * Server component. Renders up to 9 cards (icon + name + earned date) and a
 * "+N more" link when the student has more than 9. Empty state shows a
 * "keep playing" nudge instead of an empty container.
 */
import { getTranslations } from 'next-intl/server';
import type { CEAchievement } from '@/lib/chess-empire-client';

interface AchievementsProps {
  achievements: CEAchievement[];
  /** Override for tests; default 9 keeps the 3×3 grid balanced. */
  maxShown?: number;
}

function formatDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

export default async function Achievements({
  achievements,
  maxShown = 9,
}: AchievementsProps) {
  const t = await getTranslations('empire');

  if (!achievements || achievements.length === 0) {
    return (
      <section
        data-testid="empire-achievements"
        className="rounded-2xl border bg-white p-6 md:p-8 shadow-sm"
        style={{ borderColor: 'var(--brand-primary, #1a73e8)' }}
      >
        <h2
          className="text-lg md:text-xl font-semibold mb-3"
          style={{ color: 'var(--brand-primary, #0f172a)' }}
        >
          {t('achievementsTitle')}
        </h2>
        <p data-testid="empire-achievements-empty" className="text-sm text-gray-500">
          {t('achievementsEmpty')}
        </p>
      </section>
    );
  }

  const shown = achievements.slice(0, maxShown);
  const overflow = Math.max(0, achievements.length - maxShown);

  return (
    <section
      data-testid="empire-achievements"
      className="rounded-2xl border bg-white p-6 md:p-8 shadow-sm"
      style={{ borderColor: 'var(--brand-primary, #1a73e8)' }}
    >
      <h2
        className="text-lg md:text-xl font-semibold mb-4"
        style={{ color: 'var(--brand-primary, #0f172a)' }}
      >
        {t('achievementsTitle')}
      </h2>
      <ul
        data-testid="empire-achievements-grid"
        className="grid grid-cols-2 sm:grid-cols-3 gap-3"
      >
        {shown.map((a) => (
          <li
            key={a.id}
            data-testid="empire-achievement-card"
            className="rounded-xl border border-gray-200 p-3 flex flex-col items-center text-center"
          >
            {a.icon_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={a.icon_url}
                alt=""
                data-testid="empire-achievement-icon"
                className="w-10 h-10 mb-2 object-contain"
              />
            ) : (
              <span
                aria-hidden="true"
                data-testid="empire-achievement-fallback"
                className="text-3xl mb-2"
              >
                🏆
              </span>
            )}
            <div className="text-sm font-semibold text-gray-800 line-clamp-2">
              {a.name}
            </div>
            <div className="text-xs text-gray-500 mt-1">{formatDate(a.earned_at)}</div>
          </li>
        ))}
      </ul>
      {overflow > 0 && (
        <p data-testid="empire-achievements-more" className="text-sm text-gray-600 mt-3">
          {t('achievementsMore', { count: overflow })}
        </p>
      )}
    </section>
  );
}
