'use client';

import { useState } from 'react';

import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';
import { extractPaletteFromUrl } from '@/lib/color-extract';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

const PRESET_PALETTES: Array<{ name: string; primary: string; secondary: string; accent: string }> = [
  { name: 'Classic', primary: '#1a73e8', secondary: '#ffffff', accent: '#ffd700' },
  { name: 'Royal', primary: '#7b1fa2', secondary: '#ffffff', accent: '#ffd54f' },
  { name: 'Forest', primary: '#2e7d32', secondary: '#f8fafc', accent: '#cddc39' },
  { name: 'Midnight', primary: '#0f172a', secondary: '#e2e8f0', accent: '#22d3ee' },
  { name: 'Sunrise', primary: '#ea580c', secondary: '#fff7ed', accent: '#facc15' },
  { name: 'Ocean', primary: '#0369a1', secondary: '#ecfeff', accent: '#0d9488' },
];

export default function StepBrand() {
  const { payload, update } = useWizard();
  const [savingDomain, setSavingDomain] = useState(false);
  const [domainNote, setDomainNote] = useState<string | null>(null);

  async function saveBrandToOrg() {
    if (!payload.organization_id) return;
    try {
      await fetch(
        `/api/admin/organizations/${payload.organization_id}/settings`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            primary_color: payload.primary_color,
            secondary_color: payload.secondary_color,
            accent_color: payload.accent_color,
            favicon_url: payload.favicon_url,
            custom_css: payload.custom_css,
          }),
        },
      );
    } catch {
      // Server-side autosave will retry; ignore here.
    }
  }

  return (
    <SchoolOnboardingShell
      step="brand"
      title="Make it yours."
      subtitle="Brand colors apply live. Skip what you don't need — you can always edit later."
      backTo="/for-schools/start/payment"
      onNext={saveBrandToOrg}
      preview={<BrandPreviewPanel payload={payload} />}
    >
      <div className="flex flex-col gap-5">
        <fieldset>
          <legend className="text-sm font-medium text-gray-700">
            Brand palette
          </legend>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
            {PRESET_PALETTES.map(p => {
              const selected = payload.primary_color === p.primary;
              return (
                <button
                  key={p.name}
                  type="button"
                  onClick={() =>
                    update({
                      primary_color: p.primary,
                      secondary_color: p.secondary,
                      accent_color: p.accent,
                    })
                  }
                  className={`rounded-lg border p-2 text-left ${
                    selected ? 'border-blue-600 ring-2 ring-blue-100' : 'border-gray-200'
                  }`}
                >
                  <div className="flex gap-1 mb-1">
                    <span className="h-4 w-4 rounded" style={{ backgroundColor: p.primary }} />
                    <span className="h-4 w-4 rounded border border-gray-200" style={{ backgroundColor: p.secondary }} />
                    <span className="h-4 w-4 rounded" style={{ backgroundColor: p.accent }} />
                  </div>
                  <span className="text-xs text-gray-700">{p.name}</span>
                </button>
              );
            })}
          </div>
        </fieldset>

        {payload.logo_url && (
          <button
            type="button"
            onClick={async () => {
              const palette = await extractPaletteFromUrl(payload.logo_url!);
              if (palette) {
                update({
                  primary_color: palette.dominant,
                  secondary_color: palette.muted,
                  accent_color: palette.accent,
                });
                track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_COLORS_AUTODETECTED);
              }
            }}
            className="self-start text-xs rounded border border-gray-300 px-2.5 py-1 hover:bg-gray-50"
          >
            Reset to logo-detected
          </button>
        )}

        <div className="grid grid-cols-3 gap-3">
          <label className="block">
            <span className="text-xs text-gray-600">Primary</span>
            <input
              type="color"
              value={payload.primary_color || '#1a73e8'}
              onChange={e => update({ primary_color: e.target.value })}
              className="mt-1 h-9 w-full rounded border border-gray-300"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-600">Secondary</span>
            <input
              type="color"
              value={payload.secondary_color || '#ffffff'}
              onChange={e => update({ secondary_color: e.target.value })}
              className="mt-1 h-9 w-full rounded border border-gray-300"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-600">Accent</span>
            <input
              type="color"
              value={payload.accent_color || '#ffd700'}
              onChange={e => {
                update({ accent_color: e.target.value });
                track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_COLORS_OVERRIDDEN);
              }}
              className="mt-1 h-9 w-full rounded border border-gray-300"
            />
          </label>
        </div>

        <label className="block">
          <span className="text-sm font-medium text-gray-700">
            Hero headline
          </span>
          <input
            type="text"
            value={
              payload.hero_headline ??
              (payload.school_name
                ? `Welcome to ${payload.school_name} — your chess journey starts here.`
                : '')
            }
            onChange={e => update({ hero_headline: e.target.value })}
            placeholder="Welcome to your school"
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>

        {payload.tier === 'pro' && (
          <details className="rounded-lg border border-gray-200 p-3">
            <summary className="cursor-pointer text-sm font-medium text-gray-700">
              Custom domain (Pro)
            </summary>
            <div className="mt-3 space-y-2">
              <input
                type="text"
                value={payload.custom_domain || ''}
                onChange={e => update({ custom_domain: e.target.value })}
                placeholder="learn.yourdomain.com"
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 outline-none"
              />
              <p className="text-xs text-gray-500">
                You&apos;ll set up DNS in <code>/admin/settings/domain</code> after
                onboarding. The CNAME instructions are auto-generated there.
              </p>
              <button
                type="button"
                disabled={!payload.organization_id || !payload.custom_domain || savingDomain}
                onClick={async () => {
                  if (!payload.organization_id || !payload.custom_domain) return;
                  setSavingDomain(true);
                  setDomainNote(null);
                  try {
                    const res = await fetch(
                      `/api/admin/organizations/${payload.organization_id}/custom-domain`,
                      {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ domain: payload.custom_domain }),
                      },
                    );
                    setDomainNote(res.ok ? 'Reserved — finish DNS in /admin/settings/domain.' : 'Could not reserve domain.');
                  } catch {
                    setDomainNote('Could not reach the server.');
                  } finally {
                    setSavingDomain(false);
                  }
                }}
                className="text-xs rounded border border-gray-300 px-2.5 py-1 hover:bg-gray-50 disabled:opacity-50"
              >
                {savingDomain ? 'Reserving…' : 'Reserve this domain'}
              </button>
              {domainNote && (
                <p className="text-xs text-gray-700">{domainNote}</p>
              )}
            </div>
          </details>
        )}
      </div>
    </SchoolOnboardingShell>
  );
}
