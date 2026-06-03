'use client';

import { useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  parseCsv,
  detectColumnMapping,
  mapRows,
  applyTierCap,
  type ColumnMapping,
  type ValidatedRow,
} from '@/lib/csv-importer';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

// PRD §11.2 #7 — Step 6 CSV bulk importer.

type MappedColumn = 'email' | 'first_name' | 'last_name';

const COLUMN_OPTIONS: Array<{ value: MappedColumn; labelKey: string }> = [
  { value: 'email', labelKey: 'columnEmail' },
  { value: 'first_name', labelKey: 'columnFirstName' },
  { value: 'last_name', labelKey: 'columnLastName' },
];

interface Props {
  remainingSeats: number | null;
  existingEmails?: string[];
  onSubmit: (rows: ValidatedRow[]) => Promise<void> | void;
  submitting?: boolean;
}

export function CsvImporter({
  remainingSeats,
  existingEmails = [],
  onSubmit,
  submitting,
}: Props) {
  const t = useTranslations('schoolOnboarding.csv');
  const [data, setData] = useState<string[][] | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<ColumnMapping | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const ingest = useCallback((text: string) => {
    setParseError(null);
    try {
      const parsed = parseCsv(text);
      if (!parsed.length) {
        setParseError(t('noRowsError'));
        return;
      }
      const head = parsed[0];
      const detected = detectColumnMapping(head);
      if (detected.auto_detected) {
        setHeaders(head);
        setData(parsed.slice(1));
        setMapping(detected);
      } else {
        const cols = head.length;
        setHeaders(Array.from({ length: cols }, (_, i) => t('columnPositional', { n: i + 1 })));
        setData(parsed);
        setMapping({
          email: cols === 1 ? 0 : null,
          first_name: null,
          last_name: null,
          auto_detected: false,
        });
      }
      track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_CSV_PARSED, {
        rows: parsed.length,
        auto_detected: detected.auto_detected,
      });
    } catch (err) {
      setParseError(err instanceof Error ? err.message : t('parseFailed'));
    }
  }, [t]);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (!file) return;
    file.text().then(ingest);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    file.text().then(ingest);
  };

  const mapped =
    data && mapping
      ? mapRows(data, mapping, existingEmails)
      : null;
  const cap = mapped ? applyTierCap(mapped.rows, remainingSeats) : null;

  async function handleImport() {
    if (!cap) return;
    await onSubmit(cap.to_import);
  }

  function patchMapping(col: keyof ColumnMapping, idx: number | null) {
    if (!mapping) return;
    setMapping({ ...mapping, [col]: idx, auto_detected: true });
  }

  return (
    <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-800">{t('heading')}</h4>
        <label className="text-xs text-blue-600 cursor-pointer hover:underline">
          {t('pickFile')}
          <input
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileSelect}
          />
        </label>
      </div>

      <div
        onDragOver={e => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`mt-3 rounded border-2 border-dashed py-6 text-center text-xs ${
          dragOver ? 'border-blue-500 bg-blue-50' : 'border-gray-300 text-gray-500'
        }`}
      >
        {t('dropHere')}
        <button
          type="button"
          className="ml-1 text-blue-600 underline"
          onClick={() => {
            const ta = prompt(t('pastePrompt'));
            if (ta) ingest(ta);
          }}
        >
          {t('pasteContent')}
        </button>
      </div>

      {parseError && <p className="mt-2 text-xs text-red-600">{parseError}</p>}

      {mapping && data && (
        <div className="mt-3 space-y-3">
          <div>
            <div className="text-xs font-medium text-gray-600 mb-1">
              {t('mapColumns')}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
              {COLUMN_OPTIONS.map(opt => (
                <label key={opt.value} className="flex flex-col">
                  <span className="text-gray-500">{t(opt.labelKey)}</span>
                  <select
                    value={mapping[opt.value] ?? ''}
                    onChange={e =>
                      patchMapping(
                        opt.value,
                        e.target.value === '' ? null : Number(e.target.value),
                      )
                    }
                    className="mt-0.5 rounded border border-gray-300 px-1 py-1"
                  >
                    <option value="">{t('columnNone')}</option>
                    {headers.map((h, i) => (
                      <option key={i} value={i}>
                        {h}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          </div>

          {mapped && cap && (
            <div className="rounded border border-gray-200 bg-white max-h-48 overflow-x-auto overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-2 py-1 text-left">{t('tableRow')}</th>
                    <th className="px-2 py-1 text-left">{t('tableEmail')}</th>
                    <th className="px-2 py-1 text-left">{t('tableStatus')}</th>
                  </tr>
                </thead>
                <tbody>
                  {mapped.rows.map(r => {
                    const skipped = cap.skipped_for_cap.includes(r);
                    return (
                      <tr key={r.index} className="border-t">
                        <td className="px-2 py-1 text-gray-400">{r.index + 1}</td>
                        <td className="px-2 py-1 font-mono">{r.email || t('emailEmpty')}</td>
                        <td className="px-2 py-1">
                          {skipped ? (
                            <span className="text-amber-600">{t('statusTierCap')}</span>
                          ) : r.status === 'ok' ? (
                            <span className="text-green-600">{t('statusOk')}</span>
                          ) : (
                            <span className="text-red-600">{r.status}</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {mapped && cap && (
            <div className="text-xs text-gray-600">
              {t('statusCounts', {
                ready: cap.to_import.length,
                invalid: mapped.invalid_count,
                dupes: mapped.duplicate_count,
                overCap: cap.skipped_for_cap.length,
              })}
            </div>
          )}

          {cap && cap.skipped_for_cap.length > 0 && (
            <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
              <strong>{t('capWarning', { count: cap.skipped_for_cap.length })}</strong>{' '}
              <a
                href="/admin/billing"
                className="font-medium underline underline-offset-2"
              >
                {t('upgradePlan')}
              </a>
            </div>
          )}

          <button
            type="button"
            disabled={!cap || cap.to_import.length === 0 || submitting}
            onClick={handleImport}
            className="rounded bg-blue-600 px-4 h-11 text-sm font-medium text-white disabled:bg-gray-300"
          >
            {submitting ? t('importing') : t('importButton', { count: cap?.to_import.length ?? 0 })}
          </button>
        </div>
      )}
    </div>
  );
}
