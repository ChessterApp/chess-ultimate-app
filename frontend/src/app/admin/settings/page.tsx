'use client';

import { useEffect, useRef, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';
import DeleteSchoolCard from '@/components/admin/DeleteSchoolCard';
import { LogoSizePreview } from '@/components/branding/LogoSizePreview';

interface BrandingConfig {
  logo_url: string;
  logo_mark_url: string;
  favicon_url: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  custom_css: string;
  landing_page_config: {
    hero_title?: string;
    hero_subtitle?: string;
    cta_text?: string;
  };
}

type UploadKind = 'logo' | 'favicon' | 'mark';

const UPLOAD_FIELD: Record<UploadKind, keyof BrandingConfig> = {
  logo: 'logo_url',
  favicon: 'favicon_url',
  mark: 'logo_mark_url',
};

export default function AdminSettingsPage() {
  const { org } = useOrganization();
  const [config, setConfig] = useState<BrandingConfig>({
    logo_url: '',
    logo_mark_url: '',
    favicon_url: '',
    primary_color: '#1a73e8',
    secondary_color: '#ffffff',
    accent_color: '#ffd700',
    custom_css: '',
    landing_page_config: {},
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [uploadingKind, setUploadingKind] = useState<UploadKind | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const logoFileRef = useRef<HTMLInputElement | null>(null);
  const markFileRef = useRef<HTMLInputElement | null>(null);
  const faviconFileRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!org) return;
    setConfig({
      logo_url: org.logoUrl || '',
      logo_mark_url: org.logoMarkUrl || '',
      favicon_url: org.faviconUrl || '',
      primary_color: org.primaryColor,
      secondary_color: org.secondaryColor,
      accent_color: org.accentColor,
      custom_css: org.customCss || '',
      landing_page_config: (org.landingPageConfig as BrandingConfig['landing_page_config']) || {},
    });
  }, [org]);

  async function persistConfig(next: BrandingConfig) {
    if (!org?.id) return false;
    const res = await fetch(`/api/admin/organizations/${org.id}/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(next),
    });
    return res.ok;
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!org?.id) return;
    setSaving(true);
    setSaved(false);
    try {
      const ok = await persistConfig(config);
      if (ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } finally {
      setSaving(false);
    }
  }

  async function handleUpload(kind: UploadKind, file: File) {
    if (!org?.id) return;
    setUploadingKind(kind);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('kind', kind);
      const res = await fetch(`/api/admin/organizations/${org.id}/branding/upload`, {
        method: 'POST',
        body: form,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.url) {
        setUploadError(data.error || 'Upload failed');
        return;
      }
      const next: BrandingConfig = {
        ...config,
        [UPLOAD_FIELD[kind]]: data.url,
      };
      setConfig(next);
      const persisted = await persistConfig(next);
      if (persisted) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } finally {
      setUploadingKind(null);
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
        Settings
      </h1>

      <form onSubmit={handleSave} className="space-y-8 max-w-2xl">
        {/* Branding Section */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Branding</h2>

          <div className="space-y-4">
            {/* Logo URL + upload */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Logo URL
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="url"
                  value={config.logo_url}
                  onChange={e => setConfig({ ...config, logo_url: e.target.value })}
                  placeholder="https://example.com/logo.png"
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
                <input
                  ref={logoFileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) handleUpload('logo', f);
                  }}
                />
                <button
                  type="button"
                  onClick={() => logoFileRef.current?.click()}
                  disabled={uploadingKind === 'logo'}
                  className="px-3 py-2 text-sm font-medium border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                >
                  {uploadingKind === 'logo' ? 'Uploading…' : 'Upload'}
                </button>
              </div>
            </div>

            {/* Small icon (mark) URL + upload */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Small icon (square, simple)
              </label>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                Used at ≤48px (navbar, sidebar, favicon, coach avatar). Falls back
                to the logo when empty.
              </p>
              <div className="flex items-center gap-2">
                <input
                  type="url"
                  value={config.logo_mark_url}
                  onChange={e => setConfig({ ...config, logo_mark_url: e.target.value })}
                  placeholder="https://example.com/mark.png"
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
                <input
                  ref={markFileRef}
                  type="file"
                  accept="image/png,image/svg+xml,image/webp"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) handleUpload('mark', f);
                  }}
                />
                <button
                  type="button"
                  onClick={() => markFileRef.current?.click()}
                  disabled={uploadingKind === 'mark'}
                  className="px-3 py-2 text-sm font-medium border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                >
                  {uploadingKind === 'mark' ? 'Uploading…' : 'Upload'}
                </button>
              </div>
            </div>

            {/* Favicon URL + upload */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Favicon URL
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="url"
                  value={config.favicon_url}
                  onChange={e => setConfig({ ...config, favicon_url: e.target.value })}
                  placeholder="https://example.com/favicon.ico"
                  className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
                />
                <input
                  ref={faviconFileRef}
                  type="file"
                  accept="image/png,image/x-icon,image/svg+xml,image/vnd.microsoft.icon"
                  className="hidden"
                  onChange={e => {
                    const f = e.target.files?.[0];
                    if (f) handleUpload('favicon', f);
                  }}
                />
                <button
                  type="button"
                  onClick={() => faviconFileRef.current?.click()}
                  disabled={uploadingKind === 'favicon'}
                  className="px-3 py-2 text-sm font-medium border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                >
                  {uploadingKind === 'favicon' ? 'Uploading…' : 'Upload'}
                </button>
              </div>
            </div>

            {uploadError && (
              <p className="text-sm text-red-600 dark:text-red-400">{uploadError}</p>
            )}

            {/* Live small-size preview */}
            {(config.logo_url || config.logo_mark_url) && (
              <LogoSizePreview logoUrl={config.logo_url} markUrl={config.logo_mark_url} />
            )}

            {/* Colors */}
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Primary
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={config.primary_color}
                    onChange={e => setConfig({ ...config, primary_color: e.target.value })}
                    className="h-8 w-8 rounded cursor-pointer border-0"
                  />
                  <input
                    type="text"
                    value={config.primary_color}
                    onChange={e => setConfig({ ...config, primary_color: e.target.value })}
                    className="flex-1 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-xs bg-white dark:bg-gray-700"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Secondary
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={config.secondary_color}
                    onChange={e => setConfig({ ...config, secondary_color: e.target.value })}
                    className="h-8 w-8 rounded cursor-pointer border-0"
                  />
                  <input
                    type="text"
                    value={config.secondary_color}
                    onChange={e => setConfig({ ...config, secondary_color: e.target.value })}
                    className="flex-1 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-xs bg-white dark:bg-gray-700"
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Accent
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="color"
                    value={config.accent_color}
                    onChange={e => setConfig({ ...config, accent_color: e.target.value })}
                    className="h-8 w-8 rounded cursor-pointer border-0"
                  />
                  <input
                    type="text"
                    value={config.accent_color}
                    onChange={e => setConfig({ ...config, accent_color: e.target.value })}
                    className="flex-1 px-2 py-1 border border-gray-300 dark:border-gray-600 rounded text-xs bg-white dark:bg-gray-700"
                  />
                </div>
              </div>
            </div>

            {/* Custom CSS */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Custom CSS
              </label>
              <textarea
                value={config.custom_css}
                onChange={e => setConfig({ ...config, custom_css: e.target.value })}
                rows={8}
                spellCheck={false}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm font-mono"
                placeholder="/* :root { --brand-radius: 12px; } */"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Advanced — applied site-wide. Use at your own risk.
              </p>
            </div>
          </div>
        </section>

        {/* Landing Page Section */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Landing Page</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Hero Title
              </label>
              <input
                type="text"
                value={config.landing_page_config.hero_title || ''}
                onChange={e => setConfig({
                  ...config,
                  landing_page_config: { ...config.landing_page_config, hero_title: e.target.value },
                })}
                placeholder="Welcome to our chess school"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Hero Subtitle
              </label>
              <input
                type="text"
                value={config.landing_page_config.hero_subtitle || ''}
                onChange={e => setConfig({
                  ...config,
                  landing_page_config: { ...config.landing_page_config, hero_subtitle: e.target.value },
                })}
                placeholder="Learn chess with the best coaches"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                CTA Button Text
              </label>
              <input
                type="text"
                value={config.landing_page_config.cta_text || ''}
                onChange={e => setConfig({
                  ...config,
                  landing_page_config: { ...config.landing_page_config, cta_text: e.target.value },
                })}
                placeholder="Get Started"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
          </div>
        </section>

        {/* Preview Panel */}
        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Preview</h2>
          <div
            className="rounded-lg p-6 text-center"
            style={{ backgroundColor: config.primary_color }}
          >
            {config.logo_url && (
              <img src={config.logo_url} alt="Logo preview" className="h-12 mx-auto mb-3 rounded" />
            )}
            <h3 className="text-xl font-bold" style={{ color: config.secondary_color }}>
              {config.landing_page_config.hero_title || org?.name || 'Your School'}
            </h3>
            <p className="mt-1 text-sm opacity-80" style={{ color: config.secondary_color }}>
              {config.landing_page_config.hero_subtitle || 'Welcome'}
            </p>
            <button
              type="button"
              className="mt-4 px-4 py-2 rounded-lg font-medium text-sm"
              style={{ backgroundColor: config.accent_color, color: config.primary_color }}
            >
              {config.landing_page_config.cta_text || 'Get Started'}
            </button>
          </div>
        </section>

        {/* Submit */}
        <div className="flex items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors"
            style={{ backgroundColor: 'var(--brand-primary)' }}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
          {saved && (
            <span className="text-sm text-green-600 dark:text-green-400">Settings saved!</span>
          )}
        </div>
      </form>

      {/* Danger zone — self-serve school deletion (PRD §7). Kept outside the
          branding form so it's not part of the save-settings submit. */}
      {org?.id && (
        <div className="mt-12 max-w-2xl">
          <DeleteSchoolCard
            orgId={org.id}
            orgName={org.name}
            initialDeletionRequestedAt={org.deletionRequestedAt}
          />
        </div>
      )}
    </div>
  );
}
