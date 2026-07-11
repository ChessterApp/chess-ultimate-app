/**
 * Two-step Chess Empire student claim flow (client state machine).
 *
 * State transitions: `search` → `confirm` → redirect to /sign-up.
 * Keeps everything in a single component so back/forward is a state hop
 * rather than a navigation. Lives under `/welcome/[branchToken]` and
 * relies on the server wrapper to have already validated the token.
 *
 * Step 1 (search): debounced autocomplete against
 * /api/chess-empire/students/search. Renders up to 8 results.
 *
 * Step 2 (confirm): "is this you?" card built from the selected row.
 * Confirming POSTs to /api/chess-empire/students/verify. Success returns
 * an `inviteJwt` which we forward to /sign-up?invite=<jwt>. 409 →
 * redirect to the duplicate screen at /welcome/<branchToken>/registered.
 */
'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import Image from 'next/image';
import { useBranding } from '@/contexts/OrganizationContext';
import { usePhaseHistory } from '@/hooks/usePhaseHistory';

interface WelcomeFlowProps {
  branchToken: string;
  branchName: string;
  organizationId: string;
}

interface StudentResult {
  studentId: string;
  firstName: string;
  lastName: string;
  branchName: string;
  coachName: string | null;
  /** `'coach'` marks a CE coach result; absent/`'student'` is a student. */
  type?: 'student' | 'coach';
}

type Step = 'search' | 'confirm';

const DEBOUNCE_MS = 250;
const MIN_QUERY_CHARS = 2;
const MAX_VISIBLE_RESULTS = 8;

export default function WelcomeFlow({
  branchToken,
  branchName,
  organizationId,
}: WelcomeFlowProps) {
  const t = useTranslations('welcome');
  const router = useRouter();
  const branding = useBranding();
  // The org context drives header branding; in the chess-empire tenant the
  // host resolves it from the subdomain. We still pass `organizationId`
  // explicitly to keep the component testable in isolation.
  void organizationId;

  const [step, setStep] = useState<Step>('search');
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [results, setResults] = useState<StudentResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<StudentResult | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // Debounce the query.
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedQuery(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(handle);
  }, [query]);

  // Fetch results when debouncedQuery changes.
  useEffect(() => {
    if (debouncedQuery.length < MIN_QUERY_CHARS) {
      setResults(null);
      setSearching(false);
      setSearchError(null);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    setSearchError(null);
    const url = `/api/chess-empire/students/search?branchToken=${encodeURIComponent(
      branchToken,
    )}&q=${encodeURIComponent(debouncedQuery)}`;
    fetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`status_${res.status}`);
        return (await res.json()) as { results: StudentResult[] };
      })
      .then((body) => {
        setResults(body.results ?? []);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name === 'AbortError') return;
        setSearchError(t('genericError'));
        setResults([]);
      })
      .finally(() => setSearching(false));
    return () => controller.abort();
    // `t` (next-intl translator) is recreated each render — including it in the
    // dep array triggers an infinite loop. The error message is captured via the
    // closure at first run and that is stable enough for our purposes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedQuery, branchToken]);

  // Latest selection, read synchronously by the popstate restore below.
  const selectedRef = useRef(selected);
  useEffect(() => {
    selectedRef.current = selected;
  }, [selected]);

  // Rebuild the step from the URL, on mount (refresh/deep-link) and on popstate
  // (Back/Forward). The selection is in-memory only, so a refresh on
  // `?step=confirm` with nothing selected falls back to search cleanly.
  const restore = useCallback(
    (
      target: { step: Step },
      meta: { initial: boolean; replace: (p: { step: Step }) => void },
    ) => {
      if (target.step === 'confirm' && selectedRef.current) {
        setStep('confirm');
        return;
      }
      // Confirm without a selection (refresh/deep-link) → normalize the URL.
      if (target.step === 'confirm') {
        meta.replace({ step: 'search' });
      }
      setSelected(null);
      setVerifyError(null);
      setStep('search');
    },
    [],
  );

  const history = usePhaseHistory<{ step: Step }>({
    parse: (params) => ({ step: params.get('step') === 'confirm' ? 'confirm' : 'search' }),
    serialize: (p) => ({ step: p.step === 'confirm' ? 'confirm' : '' }),
    onRestore: restore,
  });

  const onSelectResult = useCallback(
    (result: StudentResult) => {
      setSelected(result);
      setVerifyError(null);
      setStep('confirm');
      history.push({ step: 'confirm' });
    },
    [history],
  );

  const onConfirmBack = useCallback(() => {
    // Pop the confirm entry; the popstate restore returns to search.
    history.back();
  }, [history]);

  const onConfirmYes = useCallback(async () => {
    if (!selected || verifying) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await fetch('/api/chess-empire/students/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          branchToken,
          studentId: selected.studentId,
          // Only sent for coaches so student request bodies stay unchanged.
          ...(selected.type === 'coach' ? { type: 'coach' } : {}),
        }),
      });
      if (res.status === 409) {
        router.replace(`/welcome/${encodeURIComponent(branchToken)}/registered`);
        return;
      }
      if (!res.ok) {
        setVerifyError(t('genericError'));
        return;
      }
      const body = (await res.json()) as { inviteJwt?: string };
      if (!body.inviteJwt) {
        setVerifyError(t('genericError'));
        return;
      }
      router.replace(`/sign-up?invite=${encodeURIComponent(body.inviteJwt)}`);
    } catch {
      setVerifyError(t('genericError'));
    } finally {
      setVerifying(false);
    }
  }, [selected, verifying, branchToken, router, t]);

  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)]">
      <div className="w-full max-w-md bg-white md:bg-white rounded-3xl md:rounded-3xl p-6 md:p-8 mt-4 md:mt-0 shadow-xl">
        <div className="text-center mb-6">
          <div className="bg-white rounded-full inline-flex items-center justify-center shadow-lg w-24 h-24 md:w-28 md:h-28 overflow-hidden">
            {branding.logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={branding.logoUrl}
                alt={branding.name}
                className="w-full h-full object-contain"
              />
            ) : (
              <Image
                src="/static/images/chesster-logo-v3.png"
                alt={branding.name}
                width={112}
                height={112}
                className="w-full h-full object-contain"
                priority
              />
            )}
          </div>
        </div>

        {step === 'search' && (
          <SearchStep
            branchName={branchName}
            query={query}
            onQueryChange={setQuery}
            searching={searching}
            results={results}
            searchError={searchError}
            onSelect={onSelectResult}
          />
        )}

        {step === 'confirm' && selected && (
          <ConfirmStep
            selected={selected}
            onYes={onConfirmYes}
            onBack={onConfirmBack}
            verifying={verifying}
            verifyError={verifyError}
          />
        )}
      </div>
    </div>
  );
}

function SearchStep({
  branchName,
  query,
  onQueryChange,
  searching,
  results,
  searchError,
  onSelect,
}: {
  branchName: string;
  query: string;
  onQueryChange: (v: string) => void;
  searching: boolean;
  results: StudentResult[] | null;
  searchError: string | null;
  onSelect: (r: StudentResult) => void;
}) {
  const t = useTranslations('welcome');
  const trimmed = query.trim();
  const tooShort = trimmed.length > 0 && trimmed.length < MIN_QUERY_CHARS;
  const visible = (results ?? []).slice(0, MAX_VISIBLE_RESULTS);
  return (
    <>
      <h1 className="text-2xl font-bold text-gray-800 text-center">
        {t('heading', { branch: branchName })}
      </h1>
      <p className="text-sm text-gray-500 mt-2 text-center">{t('subHeading')}</p>

      <div className="mt-6">
        <label htmlFor="welcome-search" className="sr-only">
          {t('searchPlaceholder')}
        </label>
        <input
          id="welcome-search"
          type="text"
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder={t('searchPlaceholder')}
          className="w-full rounded-2xl border-2 border-gray-200 py-4 px-5 text-base placeholder:text-gray-400 transition-shadow focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
        />
        {tooShort && (
          <p className="text-xs text-gray-400 mt-2">{t('minCharsHint')}</p>
        )}
      </div>

      <div className="mt-4 min-h-[120px]" role="region" aria-live="polite">
        {searching && (
          <div data-testid="welcome-search-loading" className="space-y-2">
            <SearchSkeleton />
            <SearchSkeleton />
            <SearchSkeleton />
          </div>
        )}
        {!searching && searchError && (
          <p className="text-sm text-red-500">{searchError}</p>
        )}
        {!searching && !searchError && results !== null && results.length === 0 && trimmed.length >= MIN_QUERY_CHARS && (
          <p className="text-sm text-gray-500">{t('noResults')}</p>
        )}
        {!searching && !searchError && visible.length > 0 && (
          <ul className="space-y-2" data-testid="welcome-search-results">
            {visible.map((r) => (
              <li key={r.studentId}>
                <button
                  type="button"
                  onClick={() => onSelect(r)}
                  className="w-full text-left rounded-2xl border-2 border-gray-200 bg-white hover:border-purple-400 hover:bg-purple-50 transition-all p-4 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2"
                >
                  <span className="flex items-center gap-2 font-semibold text-gray-800">
                    <span>
                      {r.firstName} {r.lastName}
                    </span>
                    {r.type === 'coach' && (
                      <span
                        data-testid="welcome-coach-badge"
                        className="inline-flex items-center rounded-full bg-purple-100 px-2 py-0.5 text-xs font-semibold text-purple-700"
                      >
                        {t('coachBadge')}
                      </span>
                    )}
                  </span>
                  {r.coachName && (
                    <span className="block text-xs text-gray-500 mt-1">
                      {t('coachLabel', { coach: r.coachName })}
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="text-xs text-gray-400 mt-6 text-center">{t('cantFind')}</p>
    </>
  );
}

function SearchSkeleton() {
  return (
    <div className="w-full rounded-2xl border-2 border-gray-100 bg-gray-50 p-4 animate-pulse">
      <div className="h-4 w-32 bg-gray-200 rounded" />
      <div className="h-3 w-20 bg-gray-100 rounded mt-2" />
    </div>
  );
}

function ConfirmStep({
  selected,
  onYes,
  onBack,
  verifying,
  verifyError,
}: {
  selected: StudentResult;
  onYes: () => void;
  onBack: () => void;
  verifying: boolean;
  verifyError: string | null;
}) {
  const t = useTranslations('welcome');
  return (
    <>
      <h1 className="text-2xl font-bold text-gray-800 text-center">
        {t('confirmTitle')}
      </h1>
      <div className="mt-6 rounded-2xl border-2 border-gray-200 p-5 text-center">
        <p className="text-xl font-semibold text-gray-900">
          {selected.firstName} {selected.lastName}
        </p>
        {selected.type === 'coach' && (
          <span
            data-testid="welcome-confirm-coach-badge"
            className="mt-2 inline-flex items-center rounded-full bg-purple-100 px-3 py-1 text-xs font-semibold text-purple-700"
          >
            {t('coachBadge')}
          </span>
        )}
        <p className="text-sm text-gray-500 mt-2">
          {t('confirmBranch', { branch: selected.branchName })}
        </p>
        {selected.coachName && (
          <p className="text-sm text-gray-500 mt-1">
            {t('confirmCoach', { coach: selected.coachName })}
          </p>
        )}
      </div>

      {verifyError && (
        <p role="alert" className="text-sm text-red-500 mt-4">
          {verifyError}
        </p>
      )}

      <button
        type="button"
        onClick={onYes}
        disabled={verifying}
        className="mt-6 w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 disabled:border-gray-400 rounded-2xl py-4 font-bold uppercase tracking-wide text-white border-b-4 border-purple-800 active:border-b-2 active:translate-y-0.5 transition-all focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-300 focus-visible:ring-offset-2"
      >
        {verifying ? t('verifying') : t('confirmYes')}
      </button>
      <button
        type="button"
        onClick={onBack}
        disabled={verifying}
        className="mt-3 w-full rounded-2xl py-3 font-semibold text-gray-500 hover:text-gray-700 disabled:text-gray-300 focus:outline-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-offset-2 transition-all"
      >
        {t('confirmBack')}
      </button>
    </>
  );
}
