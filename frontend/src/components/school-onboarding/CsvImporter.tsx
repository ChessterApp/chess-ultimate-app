'use client';

import { useState, useCallback } from 'react';
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
//
// Drag-drop + paste textbox · column auto-detect with manual override ·
// row-level preview · tier-cap-aware partial success.

type MappedColumn = 'email' | 'first_name' | 'last_name';

const COLUMN_OPTIONS: Array<{ value: MappedColumn; label: string }> = [
  { value: 'email', label: 'Email' },
  { value: 'first_name', label: 'First name' },
  { value: 'last_name', label: 'Last name' },
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
        setParseError('No rows found');
        return;
      }
      const head = parsed[0];
      const detected = detectColumnMapping(head);
      // Heuristic: if mapping detected, treat first row as header. Otherwise
      // treat the file as headerless and synthesise positional headers.
      if (detected.auto_detected) {
        setHeaders(head);
        setData(parsed.slice(1));
        setMapping(detected);
      } else {
        const cols = head.length;
        setHeaders(Array.from({ length: cols }, (_, i) => `Column ${i + 1}`));
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
      setParseError(err instanceof Error ? err.message : 'Failed to parse CSV');
    }
  }, []);

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

  // Recompute preview whenever data/mapping change. Pure.
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
        <h4 className="text-sm font-semibold text-gray-800">CSV import</h4>
        <label className="text-xs text-blue-600 cursor-pointer hover:underline">
          Pick file
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
        Drop a CSV file here, or
        <button
          type="button"
          className="ml-1 text-blue-600 underline"
          onClick={() => {
            const ta = prompt('Paste CSV content');
            if (ta) ingest(ta);
          }}
        >
          paste content
        </button>
      </div>

      {parseError && <p className="mt-2 text-xs text-red-600">{parseError}</p>}

      {mapping && data && (
        <div className="mt-3 space-y-3">
          <div>
            <div className="text-xs font-medium text-gray-600 mb-1">
              Map columns
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {COLUMN_OPTIONS.map(opt => (
                <label key={opt.value} className="flex flex-col">
                  <span className="text-gray-500">{opt.label}</span>
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
                    <option value="">— none —</option>
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
            <div className="rounded border border-gray-200 bg-white max-h-48 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-gray-50 sticky top-0">
                  <tr>
                    <th className="px-2 py-1 text-left">Row</th>
                    <th className="px-2 py-1 text-left">Email</th>
                    <th className="px-2 py-1 text-left">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {mapped.rows.map(r => {
                    const skipped = cap.skipped_for_cap.includes(r);
                    return (
                      <tr key={r.index} className="border-t">
                        <td className="px-2 py-1 text-gray-400">{r.index + 1}</td>
                        <td className="px-2 py-1 font-mono">{r.email || '(empty)'}</td>
                        <td className="px-2 py-1">
                          {skipped ? (
                            <span className="text-amber-600">tier_cap</span>
                          ) : r.status === 'ok' ? (
                            <span className="text-green-600">ok</span>
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
              {cap.to_import.length} ready · {mapped.invalid_count} invalid ·{' '}
              {mapped.duplicate_count} dupes · {cap.skipped_for_cap.length} over cap
            </div>
          )}

          {cap && cap.skipped_for_cap.length > 0 && (
            <div className="rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
              <strong>{cap.skipped_for_cap.length} row{cap.skipped_for_cap.length === 1 ? '' : 's'} skipped</strong>{' '}
              — upgrade to invite all.{' '}
              <a
                href="/admin/billing"
                className="font-medium underline underline-offset-2"
              >
                Upgrade plan →
              </a>
            </div>
          )}

          <button
            type="button"
            disabled={!cap || cap.to_import.length === 0 || submitting}
            onClick={handleImport}
            className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white disabled:bg-gray-300"
          >
            {submitting ? 'Importing…' : `Import ${cap?.to_import.length ?? 0} invites`}
          </button>
        </div>
      )}
    </div>
  );
}
