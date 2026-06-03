'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, type ReactNode } from 'react';
import { useTranslations } from 'next-intl';

import { useWizard, WIZARD_STEPS, type WizardStep } from './WizardState';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

const STEP_ROUTES: Record<WizardStep, string> = {
  account: '/for-schools/start',
  school: '/for-schools/start/school',
  plan: '/for-schools/start/plan',
  payment: '/for-schools/start/payment',
  brand: '/for-schools/start/brand',
  invite: '/for-schools/start/invite',
  done: '/for-schools/start/done',
};

const VISIBLE_STEPS: WizardStep[] = WIZARD_STEPS.filter(s => s !== 'done');

function StepDots({ current }: { current: WizardStep }) {
  const t = useTranslations('schoolOnboarding.shell');
  const idx = VISIBLE_STEPS.indexOf(current);
  return (
    <div className="flex items-center gap-1.5">
      {VISIBLE_STEPS.map((s, i) => (
        <span
          key={s}
          aria-label={t('stepAriaLabel', { index: i + 1, name: t(`stepNames.${s}`) })}
          className={`h-2 w-6 rounded-full transition-colors ${
            i <= idx ? 'bg-blue-600' : 'bg-gray-200'
          }`}
        />
      ))}
      <span className="ml-3 text-xs text-gray-500">
        {t('stepCounter', { current: idx + 1, total: VISIBLE_STEPS.length })}
      </span>
    </div>
  );
}

interface ShellProps {
  step: WizardStep;
  title: string;
  subtitle?: string;
  children: ReactNode;
  preview?: ReactNode;
  backTo?: string;
  nextLabel?: string;
  onNext?: () => void | Promise<void>;
  canAdvance?: boolean;
  /** When true, the right rail is hidden and the form spans full width. */
  hidePreview?: boolean;
}

export function SchoolOnboardingShell({
  step,
  title,
  subtitle,
  children,
  preview,
  backTo,
  nextLabel,
  onNext,
  canAdvance = true,
  hidePreview = false,
}: ShellProps) {
  const router = useRouter();
  const pathname = usePathname();
  const t = useTranslations('schoolOnboarding.shell');
  const { setStep, save } = useWizard();

  // PRD §6.8 + Phase 1 carryover #7 — emit step_viewed once per mount.
  useEffect(() => {
    track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STEP_VIEWED, { step });
  }, [step]);

  const handleSaveExit = async () => {
    await save();
    router.push('/');
  };

  const handleNext = async () => {
    if (onNext) await onNext();
    track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STEP_ADVANCED, { step });
    const idx = VISIBLE_STEPS.indexOf(step);
    if (idx >= 0 && idx + 1 < VISIBLE_STEPS.length) {
      const nextStep = VISIBLE_STEPS[idx + 1];
      setStep(nextStep);
      router.push(STEP_ROUTES[nextStep]);
    } else if (VISIBLE_STEPS.indexOf(step) === VISIBLE_STEPS.length - 1) {
      track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_COMPLETED);
    }
  };

  const resolvedNextLabel = nextLabel ?? `${t('continueDefault')} →`;

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 px-4 sm:px-6 py-3 flex items-center justify-between">
        <Link href="/" className="font-semibold text-gray-900 tracking-tight">
          {t('chesster')}
        </Link>
        <StepDots current={step} />
        <button
          type="button"
          onClick={handleSaveExit}
          className="text-sm text-gray-600 hover:text-gray-900"
        >
          {t('saveAndExit')}
        </button>
      </header>

      {/* Body */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-[45fr_55fr]">
        <section className="bg-white p-6 sm:p-10 lg:border-r border-gray-200">
          <div className="max-w-md mx-auto">
            <h1 className="text-2xl font-bold text-gray-900">{title}</h1>
            {subtitle && (
              <p className="mt-2 text-sm text-gray-600">{subtitle}</p>
            )}
            <div className="mt-6">{children}</div>
          </div>
        </section>

        {!hidePreview && (
          <aside className="bg-gradient-to-br from-slate-50 to-slate-100 p-6 sm:p-10 hidden lg:block">
            <div className="sticky top-6">{preview}</div>
          </aside>
        )}
      </main>

      {/* Footer nav */}
      <footer className="bg-white border-t border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          {backTo && (
            <Link
              href={backTo}
              className="text-sm text-gray-600 hover:text-gray-900"
            >
              {t('back')}
            </Link>
          )}
        </div>
        <button
          type="button"
          disabled={!canAdvance}
          onClick={handleNext}
          className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-5 py-3 text-white font-semibold hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed min-h-[44px]"
        >
          {resolvedNextLabel}
        </button>
      </footer>
    </div>
  );
}

export { STEP_ROUTES };
