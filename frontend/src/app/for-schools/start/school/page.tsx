'use client';

import { useEffect, useState } from 'react';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { SlugAvailabilityInput } from '@/components/school-onboarding/SlugAvailabilityInput';
import { slugify, useWizard } from '@/components/school-onboarding/WizardState';

const KIND_OPTIONS: Array<{ id: NonNullable<ReturnType<typeof useWizard>['payload']['school_kind']>; label: string }> = [
  { id: 'offline', label: 'Offline school' },
  { id: 'online', label: 'Online school' },
  { id: 'solo', label: 'Solo coach' },
  { id: 'tournament', label: 'Tournament organizer' },
];

export default function StepSchool() {
  const { payload, update } = useWizard();
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
      title="What's your school called?"
      subtitle="Pick a name and a URL. You can change the colors next."
      backTo="/for-schools/start"
      canAdvance={canAdvance}
      preview={<BrandPreviewPanel payload={payload} />}
    >
      <div className="flex flex-col gap-5">
        <label className="block">
          <span className="text-sm font-medium text-gray-700">School name</span>
          <input
            type="text"
            value={payload.school_name || ''}
            onChange={e => update({ school_name: e.target.value })}
            placeholder="Almaty Chess Academy"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>

        <div>
          <span className="text-sm font-medium text-gray-700">Your URL</span>
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
            What kind of school are you?
          </legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {KIND_OPTIONS.map(opt => {
              const selected = payload.school_kind === opt.id;
              return (
                <button
                  key={opt.id}
                  type="button"
                  onClick={() => update({ school_kind: opt.id })}
                  className={`rounded-full px-3 py-1.5 text-sm border ${
                    selected
                      ? 'bg-blue-600 text-white border-blue-600'
                      : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </fieldset>

        <label className="block">
          <span className="text-sm font-medium text-gray-700">
            Logo URL <span className="text-gray-400">(optional — drag-drop upload comes after payment)</span>
          </span>
          <input
            type="url"
            value={payload.logo_url || ''}
            onChange={e => update({ logo_url: e.target.value })}
            placeholder="https://yourschool.com/logo.png"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>
      </div>
    </SchoolOnboardingShell>
  );
}
