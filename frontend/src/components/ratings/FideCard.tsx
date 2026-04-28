'use client';

interface FideData {
  fide_id: string;
  fide_standard?: number | null;
  fide_rapid?: number | null;
  fide_blitz?: number | null;
  fide_title?: string | null;
  last_synced_at?: string | null;
}

interface FideCardProps {
  fide: FideData | null;
  className?: string;
}

export default function FideCard({ fide, className = '' }: FideCardProps) {
  if (!fide) {
    return (
      <div className={`rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 ${className}`}>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">FIDE Profile</h3>
        <p className="text-sm text-gray-500 dark:text-gray-400">No FIDE ID linked</p>
      </div>
    );
  }

  return (
    <div className={`rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 ${className}`}>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">FIDE Profile</h3>
        {fide.fide_title && (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300">
            {fide.fide_title}
          </span>
        )}
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">FIDE ID: {fide.fide_id}</p>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Standard</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {fide.fide_standard ?? '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Rapid</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {fide.fide_rapid ?? '—'}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 dark:text-gray-400">Blitz</p>
          <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {fide.fide_blitz ?? '—'}
          </p>
        </div>
      </div>

      {fide.last_synced_at && (
        <p className="text-xs text-gray-400 dark:text-gray-500 mt-3">
          Last synced: {new Date(fide.last_synced_at).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
