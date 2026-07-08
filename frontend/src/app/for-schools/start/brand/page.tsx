'use client';

import { useRef, useState } from 'react';
import { useTranslations } from 'next-intl';

import { LogoSizePreview } from '@/components/branding/LogoSizePreview';
import { BrandPreviewPanel } from '@/components/school-onboarding/BrandPreviewPanel';
import { SchoolOnboardingShell } from '@/components/school-onboarding/SchoolOnboardingShell';
import { useWizard } from '@/components/school-onboarding/WizardState';
import { extractPaletteFromUrl } from '@/lib/color-extract';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

const PRESET_PALETTES: Array<{
  id: 'classic' | 'royal' | 'forest' | 'midnight' | 'sunrise' | 'ocean';
  labelKey: string;
  primary: string;
  secondary: string;
  accent: string;
}> = [
  { id: 'classic', labelKey: 'paletteClassic', primary: '#1a73e8', secondary: '#ffffff', accent: '#ffd700' },
  { id: 'royal', labelKey: 'paletteRoyal', primary: '#7b1fa2', secondary: '#ffffff', accent: '#ffd54f' },
  { id: 'forest', labelKey: 'paletteForest', primary: '#2e7d32', secondary: '#f8fafc', accent: '#cddc39' },
  { id: 'midnight', labelKey: 'paletteMidnight', primary: '#0f172a', secondary: '#e2e8f0', accent: '#22d3ee' },
  { id: 'sunrise', labelKey: 'paletteSunrise', primary: '#ea580c', secondary: '#fff7ed', accent: '#facc15' },
  { id: 'ocean', labelKey: 'paletteOcean', primary: '#0369a1', secondary: '#ecfeff', accent: '#0d9488' },
];

export default function StepBrand() {
  const { payload, update } = useWizard();
  const t = useTranslations('schoolOnboarding.brand');
  const [savingDomain, setSavingDomain] = useState(false);
  const [domainNote, setDomainNote] = useState<string | null>(null);
  const [uploadingMark, setUploadingMark] = useState(false);
  const [markError, setMarkError] = useState<string | null>(null);
  const markFileRef = useRef<HTMLInputElement | null>(null);

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
            logo_url: payload.logo_url ?? null,
            logo_mark_url: payload.logo_mark_url ?? null,
          }),
        },
      );
    } catch {
      // Server-side autosave will retry; ignore here.
    }
  }

  // Small icon (mark) goes straight to Supabase Storage via the shared branding
  // upload route so it lands in the org's folder next to logo-mark.png.
  async function uploadMark(file: File) {
    if (!payload.organization_id) return;
    setUploadingMark(true);
    setMarkError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('kind', 'mark');
      const res = await fetch(
        `/api/admin/organizations/${payload.organization_id}/branding/upload`,
        { method: 'POST', body: form },
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.url) {
        setMarkError(data.error || 'Upload failed');
        return;
      }
      update({ logo_mark_url: data.url });
    } finally {
      setUploadingMark(false);
    }
  }

  return (
    <SchoolOnboardingShell
      step="brand"
      title={t('title')}
      subtitle={t('subtitle')}
      backTo="/for-schools/start/payment"
      onNext={saveBrandToOrg}
      preview={<BrandPreviewPanel payload={payload} />}
    >
      <div className="flex flex-col gap-5">
        <fieldset>
          <legend className="text-sm font-medium text-gray-700">
            {t('paletteLegend')}
          </legend>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 gap-2">
            {PRESET_PALETTES.map(p => {
              const selected = payload.primary_color === p.primary;
              return (
                <button
                  key={p.id}
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
                  <span className="text-xs text-gray-700">{t(p.labelKey)}</span>
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
            {t('resetLogoDetected')}
          </button>
        )}

        {/* Small icon (mark) — square, simple; used at ≤48px render sites */}
        <div className="rounded-lg border border-gray-200 p-3">
          <span className="text-sm font-medium text-gray-700">
            Small icon <span className="text-gray-400">(square, simple — optional)</span>
          </span>
          <p className="mt-0.5 text-xs text-gray-500">
            Shown at ≤48px (navbar, sidebar, favicon). Falls back to your logo if empty.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <input
              ref={markFileRef}
              type="file"
              accept="image/png,image/svg+xml,image/webp"
              className="hidden"
              onChange={e => {
                const f = e.target.files?.[0];
                if (f) uploadMark(f);
              }}
            />
            <button
              type="button"
              onClick={() => markFileRef.current?.click()}
              disabled={!payload.organization_id || uploadingMark}
              className="text-xs rounded border border-gray-300 px-2.5 py-1 hover:bg-gray-50 disabled:opacity-50"
            >
              {uploadingMark ? 'Uploading…' : payload.logo_mark_url ? 'Replace icon' : 'Upload icon'}
            </button>
            {payload.logo_mark_url && (
              <button
                type="button"
                onClick={() => update({ logo_mark_url: undefined })}
                className="text-xs text-gray-500 underline hover:text-gray-700"
              >
                Remove
              </button>
            )}
          </div>
          {markError && <p className="mt-1 text-xs text-red-600">{markError}</p>}
        </div>

        {(payload.logo_url || payload.logo_mark_url) && (
          <LogoSizePreview logoUrl={payload.logo_url} markUrl={payload.logo_mark_url} />
        )}

        <div className="grid grid-cols-3 gap-3">
          <label className="block">
            <span className="text-xs text-gray-600">{t('primary')}</span>
            <span className="block text-[10px] text-gray-500">{t('primarySublabel')}</span>
            <input
              type="color"
              value={payload.primary_color || '#1a73e8'}
              onChange={e => update({ primary_color: e.target.value })}
              className="mt-1 h-9 w-full rounded border border-gray-300"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-600">{t('secondary')}</span>
            <span className="block text-[10px] text-gray-500">{t('secondarySublabel')}</span>
            <input
              type="color"
              value={payload.secondary_color || '#ffffff'}
              onChange={e => update({ secondary_color: e.target.value })}
              className="mt-1 h-9 w-full rounded border border-gray-300"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-600">{t('accent')}</span>
            <span className="block text-[10px] text-gray-500">{t('accentSublabel')}</span>
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
          <span className="text-sm font-medium text-gray-700">{t('heroLabel')}</span>
          <input
            type="text"
            value={
              payload.hero_headline ??
              (payload.school_name
                ? t('heroDefault', { schoolName: payload.school_name })
                : '')
            }
            onChange={e => update({ hero_headline: e.target.value })}
            placeholder={t('heroPlaceholder')}
            className="mt-1 block w-full rounded-lg border border-gray-300 px-3 py-2 focus:border-blue-500 focus:ring-2 focus:ring-blue-100 outline-none"
          />
        </label>

        {payload.tier === 'pro' && (
          <details className="rounded-lg border border-gray-200 p-3">
            <summary className="cursor-pointer text-sm font-medium text-gray-700">
              {t('customDomainTitle')}
            </summary>
            <div className="mt-3 space-y-2">
              <input
                type="text"
                value={payload.custom_domain || ''}
                onChange={e => update({ custom_domain: e.target.value })}
                placeholder={t('customDomainPlaceholder')}
                className="block w-full rounded-lg border border-gray-300 px-3 py-2 outline-none"
              />
              <p className="text-xs text-gray-500">
                {t.rich('customDomainHelp', {
                  code: chunks => <code>{chunks}</code>,
                })}
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
                    setDomainNote(res.ok ? t('reserveSuccess') : t('reserveFailed'));
                  } catch {
                    setDomainNote(t('reserveServerUnreachable'));
                  } finally {
                    setSavingDomain(false);
                  }
                }}
                className="text-xs rounded border border-gray-300 px-2.5 py-1 hover:bg-gray-50 disabled:opacity-50"
              >
                {savingDomain ? t('reserving') : t('reserveDomain')}
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
