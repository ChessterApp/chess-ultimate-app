'use client';

import { useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

interface BrandingConfig {
  logo_url: string;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  landing_page_config: {
    hero_title?: string;
    hero_subtitle?: string;
    cta_text?: string;
  };
}

export default function AdminSettingsPage() {
  const { org } = useOrganization();
  const [config, setConfig] = useState<BrandingConfig>({
    logo_url: '',
    primary_color: '#1a73e8',
    secondary_color: '#ffffff',
    accent_color: '#ffd700',
    landing_page_config: {},
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!org) return;
    setConfig({
      logo_url: org.logoUrl || '',
      primary_color: org.primaryColor,
      secondary_color: org.secondaryColor,
      accent_color: org.accentColor,
      landing_page_config: (org.landingPageConfig as BrandingConfig['landing_page_config']) || {},
    });
  }, [org]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!org?.id) return;
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 3000);
      }
    } finally {
      setSaving(false);
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
            {/* Logo URL */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Logo URL
              </label>
              <input
                type="url"
                value={config.logo_url}
                onChange={e => setConfig({ ...config, logo_url: e.target.value })}
                placeholder="https://example.com/logo.png"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>

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
    </div>
  );
}
