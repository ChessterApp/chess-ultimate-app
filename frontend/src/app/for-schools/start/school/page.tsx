'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { LogoDropzone } from '@/components/school-onboarding/LogoDropzone';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { SlugAvailabilityInput } from '@/components/school-onboarding/SlugAvailabilityInput';
import { slugify, useWizard } from '@/components/school-onboarding/WizardState';

type SchoolKind = NonNullable<ReturnType<typeof useWizard>['payload']['school_kind']>;
const KIND_IDS: SchoolKind[] = ['offline', 'online', 'solo', 'tournament'];
const KIND_LABEL_KEYS: Record<SchoolKind, string> = {
  offline: 'kindOffline',
  online: 'kindOnline',
  solo: 'kindSolo',
  tournament: 'kindTournament',
};

export default function StepSchool() {
  const { payload, update } = useWizard();
  const t = useTranslations('schoolOnboarding.school');
  const [slugAvailable, setSlugAvailable] = useState(false);
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false);

  // Auto-derive slug from school name until the user edits it manually
  useEffect(() => {
    if (!slugManuallyEdited && payload.school_name) {
      const derived = slugify(payload.school_name);
      if (derived && derived !== payload.slug) update({ slug: derived });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [payload.school_name]);

  const canAdvance = Boolean(payload.school_name && payload.slug && slugAvailable);

  return (
    <SchoolOnboardingShell
      step="school"
      title={t('title')}
      subtitle={t('subtitle')}
      backTo="/for-schools/start"
      canAdvance={canAdvance}
      preview={<BrandPreviewPanel payload={payload} />}
    >
      <div className="flex flex-col gap-5">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">{t('nameLabel')}</span>
          <input
            type="text"
            value={payload.school_name || ''}
            onChange={e => update({ school_name: e.target.value })}
            placeholder={t('namePlaceholder')}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>

        <div>
          <span className="text-sm font-medium text-gray-700">{t('urlLabel')}</span>
          <div className="mt-1">
            <SlugAvailabilityInput
              value={payload.slug || ''}
              onChange={next => {
                setSlugManuallyEdited(true);
                update({ slug: slugify(next) });
              }}
              onAvailabilityChange={setSlugAvailable}
            />
          </div>
        </div>

        <fieldset>
          <legend className="text-sm font-medium text-gray-700">
            {t('kindLegend')}
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {KIND_IDS.map(id => {
              const selected = payload.school_kind === id;
              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => update({ school_kind: id })}
                  className={`rounded-full px-3 py-1.5 text-sm border ${
                    selected
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'
                  }`}
                >
                  {t(KIND_LABEL_KEYS[id])}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div>
          <span className="text-sm font-medium text-gray-700">
            {t('logoLabel')} <span className="text-gray-400">{t('logoOptional')}</span>
          </span>
          <div className="mt-1">
            <LogoDropzone
              value={payload.logo_url}
              onChange={dataUrl => update({ logo_url: dataUrl })}
              onPaletteExtracted={p =>
                update({
                  primary_color: p.primary,
                  secondary_color: p.secondary,
                  accent_color: p.accent,
                })
              }
            />
          </div>
          <input
            type="url"
            value={payload.logo_url || ''}
            onChange={e => update({ logo_url: e.target.value })}
            placeholder={t('logoUrlPlaceholder')}
            className="mt-2 block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </div>
      </div>
    </SchoolOnboardingShell>
  );
}
