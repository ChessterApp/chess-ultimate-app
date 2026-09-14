'use client';

import React, { useReducer, useState } from 'react';
import { useTranslations } from 'next-intl';
import type { WheelPreset, WheelSegment } from '@/lib/wheel/types';
import { editorReducer } from '@/lib/wheel/reducer';
import { MAX_SEGMENTS, MIN_SEGMENTS } from '@/lib/wheel/presets';
import type { UsePresets } from './usePresets';

interface ConfigEditorProps {
  presetsApi: UsePresets;
  onClose: () => void;
}

export default function ConfigEditor({ presetsApi, onClose }: ConfigEditorProps) {
  const t = useTranslations('wheel');
  const {
    presets,
    current,
    currentId,
    offline,
    selectPreset,
    createPreset,
    duplicatePreset,
    deletePreset,
    savePreset,
  } = presetsApi;

  const [segments, dispatch] = useReducer(
    editorReducer,
    current?.segments ?? [],
  );
  const [name, setName] = useState(current?.name ?? '');
  const [saving, setSaving] = useState(false);

  // Re-seed the local draft when the selected preset changes.
  const [lastPresetId, setLastPresetId] = useState(currentId);
  if (currentId !== lastPresetId) {
    setLastPresetId(currentId);
    dispatch({ type: 'reset', segments: current?.segments ?? [] });
    setName(current?.name ?? '');
  }

  const handleSave = async () => {
    setSaving(true);
    try {
      await savePreset(name.trim() || t('untitled'), segments);
    } finally {
      setSaving(false);
    }
    onClose();
  };

  return (
    <div className="mx-auto w-full max-w-xl rounded-2xl bg-[#1c1230] p-4 text-white shadow-xl sm:p-6">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-bold">{t('editorTitle')}</h2>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-white/60 hover:text-white"
        >
          {t('close')}
        </button>
      </div>

      {offline && (
        <p className="mb-3 rounded-lg bg-amber-500/20 px-3 py-2 text-xs text-amber-200">
          {t('offlineNote')}
        </p>
      )}

      {/* Preset picker */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="text-sm text-white/70" htmlFor="wheel-preset-select">
          {t('presetLabel')}
        </label>
        <select
          id="wheel-preset-select"
          value={currentId ?? ''}
          onChange={(e) => selectPreset(e.target.value)}
          className="rounded-lg bg-[#2a1d45] px-3 py-1.5 text-sm"
        >
          {presets.map((p: WheelPreset) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => createPreset(t('newPresetName'))}
          className="rounded-lg bg-[#2a1d45] px-3 py-1.5 text-sm hover:bg-[#3a2a5c]"
        >
          {t('newPreset')}
        </button>
        <button
          type="button"
          onClick={() => currentId && duplicatePreset(currentId)}
          className="rounded-lg bg-[#2a1d45] px-3 py-1.5 text-sm hover:bg-[#3a2a5c]"
        >
          {t('duplicate')}
        </button>
        <button
          type="button"
          onClick={() => currentId && deletePreset(currentId)}
          disabled={presets.length <= 1}
          className="rounded-lg bg-red-600/70 px-3 py-1.5 text-sm hover:bg-red-600 disabled:opacity-40"
        >
          {t('delete')}
        </button>
      </div>

      {/* Name */}
      <div className="mb-4">
        <label className="mb-1 block text-sm text-white/70" htmlFor="wheel-name">
          {t('nameLabel')}
        </label>
        <input
          id="wheel-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-full rounded-lg bg-[#2a1d45] px-3 py-2 text-sm"
          placeholder={t('namePlaceholder')}
        />
      </div>

      {/* Segments */}
      <div className="mb-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-white/70">
            {t('segmentsLabel', { count: segments.length })}
          </span>
          <button
            type="button"
            onClick={() => dispatch({ type: 'add' })}
            disabled={segments.length >= MAX_SEGMENTS}
            className="rounded-lg bg-emerald-600/80 px-3 py-1 text-sm hover:bg-emerald-600 disabled:opacity-40"
          >
            {t('addSegment')}
          </button>
        </div>

        <div className="max-h-[40vh] space-y-2 overflow-y-auto pr-1">
          {segments.map((s: WheelSegment, i: number) => (
            <div key={s.id} className="flex items-center gap-2 rounded-lg bg-[#241735] p-2">
              <input
                type="color"
                value={s.color}
                onChange={(e) =>
                  dispatch({ type: 'update', id: s.id, patch: { color: e.target.value } })
                }
                aria-label={t('colorLabel')}
                className="h-8 w-8 shrink-0 cursor-pointer rounded border-0 bg-transparent"
              />
              <input
                type="text"
                value={s.emoji ?? ''}
                onChange={(e) =>
                  dispatch({ type: 'update', id: s.id, patch: { emoji: e.target.value || undefined } })
                }
                aria-label={t('emojiLabel')}
                placeholder="🎁"
                className="w-12 shrink-0 rounded bg-[#2a1d45] px-2 py-1.5 text-center text-sm"
              />
              <input
                type="text"
                value={s.label}
                onChange={(e) =>
                  dispatch({ type: 'update', id: s.id, patch: { label: e.target.value } })
                }
                aria-label={t('labelLabel')}
                placeholder={t('labelPlaceholder')}
                className="min-w-0 flex-1 rounded bg-[#2a1d45] px-2 py-1.5 text-sm"
              />
              <button
                type="button"
                onClick={() => dispatch({ type: 'move', id: s.id, direction: 'up' })}
                disabled={i === 0}
                aria-label={t('moveUp')}
                className="px-1 text-white/60 hover:text-white disabled:opacity-30"
              >
                ↑
              </button>
              <button
                type="button"
                onClick={() => dispatch({ type: 'move', id: s.id, direction: 'down' })}
                disabled={i === segments.length - 1}
                aria-label={t('moveDown')}
                className="px-1 text-white/60 hover:text-white disabled:opacity-30"
              >
                ↓
              </button>
              <button
                type="button"
                onClick={() => dispatch({ type: 'remove', id: s.id })}
                disabled={segments.length <= MIN_SEGMENTS}
                aria-label={t('removeSegment')}
                className="px-1 text-red-400 hover:text-red-300 disabled:opacity-30"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-full px-5 py-2 text-sm text-white/70 hover:text-white"
        >
          {t('cancel')}
        </button>
        <button
          type="button"
          onClick={handleSave}
          disabled={saving}
          className="rounded-full bg-emerald-600 px-6 py-2 text-sm font-bold hover:bg-emerald-500 disabled:opacity-50"
        >
          {saving ? t('saving') : t('save')}
        </button>
      </div>
    </div>
  );
}
