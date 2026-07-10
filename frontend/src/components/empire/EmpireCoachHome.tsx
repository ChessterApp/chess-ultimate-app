/**
 * Chess Empire personalized homepage — coach variant.
 *
 * Coaches link through the same invite flow as students but their UUID lives
 * in the CE `coaches` table, so the student profile API 404s for them. This
 * variant renders a coach-appropriate greeting with no rating/rank sections
 * (which require a student profile). Name comes exclusively from the resolved
 * coach display name; `null` degrades to a name-less greeting.
 */
import { getTranslations } from 'next-intl/server';

const ACCENT = '#10B981';

function initialFrom(name: string | null): string {
  if (!name) return '?';
  const trimmed = name.trim();
  return trimmed ? trimmed.slice(0, 1).toUpperCase() : '?';
}

export default async function EmpireCoachHome({
  coachDisplayName,
}: {
  coachDisplayName: string | null;
}) {
  const t = await getTranslations('empire');
  const greeting = coachDisplayName
    ? t('coachWelcomeNamed', { name: coachDisplayName })
    : t('coachWelcome');

  return (
    <main
      data-testid="empire-home-coach"
      className="min-h-screen px-4 sm:px-6 lg:px-10 py-8 lg:py-12"
      style={{ backgroundColor: '#F6F7F9', color: '#0F172A' }}
    >
      <div className="max-w-5xl mx-auto flex flex-col gap-6">
        <section
          data-testid="empire-coach-hero"
          className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-slate-900 to-slate-700 shadow-sm text-white"
        >
          <div className="p-6 sm:p-8 flex flex-col sm:flex-row sm:items-center gap-6">
            <div
              className="shrink-0 w-24 h-24 rounded-full grid place-items-center text-2xl font-bold ring-4"
              style={{
                background: `linear-gradient(135deg, ${ACCENT}, #0EA5A5)`,
                boxShadow: `0 0 0 3px rgba(16,185,129,0.35)`,
                ['--tw-ring-color' as string]: ACCENT,
              }}
            >
              {initialFrom(coachDisplayName)}
            </div>
            <div className="flex-1 min-w-0">
              <span className="text-xs uppercase tracking-wider text-slate-400 font-medium">
                {t('coachRoleLabel')}
              </span>
              <h1
                data-testid="empire-coach-greeting"
                className="text-2xl sm:text-3xl font-semibold tracking-tight leading-tight mt-1"
              >
                {greeting}
              </h1>
              <p className="mt-3 text-sm text-slate-300">
                {t('coachHomeSubtitle')}
              </p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
