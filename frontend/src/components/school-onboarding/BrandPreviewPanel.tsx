'use client';

import { useState } from 'react';
import type { WizardPayload } from './WizardState';

// PRD §5 (Phase 1) — preview surfaces:
//   Dashboard · Courses · Puzzles · Login.
//
// We avoid an iframe to <slug>.chesster.io here because the slug only exists
// after step 2 has saved and step 4 has paid. Instead we render an inline
// "browser-chrome" mock that consumes the same brand colors via inline CSS
// variables — exactly what the live dashboard would look like.

const TABS = ['Dashboard', 'Courses', 'Puzzles', 'Login'] as const;
type Tab = (typeof TABS)[number];

interface Props {
  payload: WizardPayload;
}

export function BrandPreviewPanel({ payload }: Props) {
  const [tab, setTab] = useState<Tab>('Dashboard');
  const slug = payload.slug || 'yourschool';
  const name = payload.school_name || 'Your School';
  const primary = payload.primary_color || '#1a73e8';
  const secondary = payload.secondary_color || '#ffffff';
  const accent = payload.accent_color || '#ffd700';
  const logo = payload.logo_url;

  return (
    <div
      className="rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden"
      style={
        {
          ['--brand-primary' as never]: primary,
          ['--brand-secondary' as never]: secondary,
          ['--brand-accent' as never]: accent,
        } as React.CSSProperties
      }
    >
      {/* Browser chrome */}
      <div className="bg-gray-100 border-b border-gray-200 px-3 py-2 flex items-center gap-2">
        <div className="flex gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
        </div>
        <div className="flex-1 bg-white rounded px-3 py-1 text-xs text-gray-500 truncate">
          https://{slug}.chesster.io
        </div>
      </div>

      {/* Mock app shell */}
      <div className="bg-white">
        <div
          className="px-4 py-3 flex items-center gap-3 border-b border-gray-200"
          style={{ backgroundColor: primary, color: secondary }}
        >
          {logo ? (
            <img
              src={logo}
              alt=""
              className="h-7 w-7 rounded bg-white object-contain"
            />
          ) : (
            <span className="h-7 w-7 rounded bg-white/20" />
          )}
          <span className="font-semibold tracking-tight">{name}</span>
          <span className="ml-auto h-6 w-6 rounded-full bg-white/30" />
        </div>

        {/* Tab strip */}
        <div className="flex border-b border-gray-200">
          {TABS.map(t => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className="px-3 py-2 text-xs font-medium border-b-2 -mb-px"
              style={{
                borderColor: tab === t ? primary : 'transparent',
                color: tab === t ? primary : '#64748b',
              }}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="p-4 min-h-[220px]">
          {tab === 'Dashboard' && (
            <div className="space-y-3">
              <div className="rounded-lg border border-gray-200 p-3">
                <div className="text-xs uppercase tracking-wide text-gray-500">
                  Welcome
                </div>
                <div className="font-semibold mt-1">
                  {payload.full_name ? `Hi, ${payload.full_name}` : 'Hi, Coach'}
                </div>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                {[1, 2, 3].map(i => (
                  <div
                    key={i}
                    className="h-16 rounded-lg"
                    style={{
                      background: `linear-gradient(135deg, ${primary}11, ${accent}22)`,
                    }}
                  />
                ))}
              </div>
            </div>
          )}
          {tab === 'Courses' && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {[1, 2, 3, 4].map(i => (
                <div
                  key={i}
                  className="aspect-video rounded-lg border border-gray-200 p-2 text-xs text-gray-500"
                >
                  Course {i}
                </div>
              ))}
            </div>
          )}
          {tab === 'Puzzles' && (
            <div className="grid grid-cols-8 gap-0.5 mx-auto w-fit">
              {Array.from({ length: 64 }).map((_, i) => (
                <span
                  key={i}
                  className="h-5 w-5 inline-block"
                  style={{
                    background:
                      (Math.floor(i / 8) + (i % 8)) % 2 === 0 ? '#eee' : primary,
                  }}
                />
              ))}
            </div>
          )}
          {tab === 'Login' && (
            <div className="rounded-lg border border-gray-200 p-4 max-w-xs mx-auto text-center">
              {logo && (
                <img
                  src={logo}
                  alt=""
                  className="mx-auto h-10 w-10 rounded bg-white object-contain"
                />
              )}
              <div className="mt-3 font-semibold text-sm">Sign in to {name}</div>
              <div className="mt-3 h-8 rounded bg-gray-100" />
              <div className="mt-2 h-8 rounded bg-gray-100" />
              <button
                type="button"
                className="mt-3 w-full rounded py-2 text-sm font-medium"
                style={{ backgroundColor: primary, color: secondary }}
              >
                Continue
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
