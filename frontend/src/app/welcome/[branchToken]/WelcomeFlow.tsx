/**
 * Three-step Chess Empire student claim flow (client state machine).
 *
 * State transitions: `search` → `confirm` → `dob` → redirect to /sign-up.
 * Keeps everything in a single component so back/forward is a state hop
 * rather than a navigation. Lives under `/welcome/[branchToken]` and
 * relies on the server wrapper to have already validated the token.
 *
 * Step 1 (search): debounced autocomplete against
 * /api/chess-empire/students/search. Renders up to 8 results.
 *
 * Step 2 (confirm): pure "is this you?" card built from the selected row.
 *
 * Step 3 (dob): three numeric inputs (DD / MM / YYYY) → POST to
 * /api/chess-empire/students/verify. Success returns an `inviteJwt` which
 * we forward to /sign-up?invite=<jwt>. 409 → redirect to the duplicate
 * screen at /welcome/<branchToken>/registered. Three in-page DOB failures
 * lock the form.
 */
'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import Image from 'next/image';
import { useBranding } from '@/contexts/OrganizationContext';

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
}

type Step = 'search' | 'confirm' | 'dob';

const DEBOUNCE_MS = 250;
const MIN_QUERY_CHARS = 2;
const MAX_VISIBLE_RESULTS = 8;
const MAX_DOB_ATTEMPTS = 3;

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
  const [dobDay, setDobDay] = useState('');
  const [dobMonth, setDobMonth] = useState('');
  const [dobYear, setDobYear] = useState('');
  const [verifying, setVerifying] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);
  const [attemptCount, setAttemptCount] = useState(0);

  const dayRef = useRef<HTMLInputElement>(null);
  const monthRef = useRef<HTMLInputElement>(null);
  const yearRef = useRef<HTMLInputElement>(null);

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

  const onSelectResult = useCallback((result: StudentResult) => {
    setSelected(result);
    setStep('confirm');
  }, []);

  const onConfirmYes = useCallback(() => {
    setStep('dob');
    // Defer to next tick so the input exists.
    setTimeout(() => dayRef.current?.focus(), 0);
  }, []);

  const onConfirmBack = useCallback(() => {
    setSelected(null);
    setStep('search');
  }, []);

  const dobValid = useMemo(() => {
    const d = parseInt(dobDay, 10);
    const m = parseInt(dobMonth, 10);
    const y = parseInt(dobYear, 10);
    if (Number.isNaN(d) || Number.isNaN(m) || Number.isNaN(y)) return false;
    if (d < 1 || d > 31) return false;
    if (m < 1 || m > 12) return false;
    if (y < 1900 || y > 2100) return false;
    return true;
  }, [dobDay, dobMonth, dobYear]);

  const locked = attemptCount >= MAX_DOB_ATTEMPTS;

  const onVerify = useCallback(async () => {
    if (!selected || !dobValid || locked || verifying) return;
    const dobIso = `${dobYear.padStart(4, '0')}-${dobMonth.padStart(2, '0')}-${dobDay.padStart(2, '0')}`;
    setVerifying(true);
    setVerifyError(null);
    try {
      const res = await fetch('/api/chess-empire/students/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          branchToken,
          studentId: selected.studentId,
          dob: dobIso,
        }),
      });
      if (res.status === 409) {
        router.replace(`/welcome/${encodeURIComponent(branchToken)}/registered`);
        return;
      }
      if (!res.ok) {
        setAttemptCount((n) => n + 1);
        setVerifyError(t('dobError'));
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
  }, [
    selected,
    dobValid,
    locked,
    verifying,
    dobDay,
    dobMonth,
    dobYear,
    branchToken,
    router,
    t,
  ]);

  const handleDigitChange =
    (setter: (v: string) => void, maxLen: number, nextRef?: React.RefObject<HTMLInputElement | null>) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const cleaned = e.target.value.replace(/\D/g, '').slice(0, maxLen);
      setter(cleaned);
      setVerifyError(null);
      if (cleaned.length === maxLen && nextRef?.current) {
        nextRef.current.focus();
      }
    };

  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)]">
      <div className="w-full max-w-md bg-white md:bg-white rounded-3xl md:rounded-3xl p-6 md:p-8 mt-4 md:mt-0 shadow-xl">
        <div className="text-center mb-6">
          <div className="bg-white rounded-full p-3 md:p-4 inline-block shadow-lg">
            {branding.logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={branding.logoUrl}
                alt={branding.name}
                className="w-10 h-10 md:w-16 md:h-16 object-contain"
              />
            ) : (
              <Image
                src="/static/images/chesster-logo-v3.png"
                alt={branding.name}
                width={64}
                height={64}
                className="w-10 h-10 md:w-16 md:h-16"
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
          />
        )}

        {step === 'dob' && selected && (
          <DobStep
            selected={selected}
            dobDay={dobDay}
            dobMonth={dobMonth}
            dobYear={dobYear}
            dayRef={dayRef}
            monthRef={monthRef}
            yearRef={yearRef}
            onDayChange={handleDigitChange(setDobDay, 2, monthRef)}
            onMonthChange={handleDigitChange(setDobMonth, 2, yearRef)}
            onYearChange={handleDigitChange(setDobYear, 4)}
            dobValid={dobValid}
            verifying={verifying}
            verifyError={verifyError}
            locked={locked}
            onVerify={onVerify}
            onBack={() => {
              setVerifyError(null);
              setStep('confirm');
            }}
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
          className="w-full rounded-2xl border-2 border-gray-200 py-4 px-5 text-base focus:border-purple-500 focus:outline-none"
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
                  className="w-full text-left rounded-2xl border-2 border-gray-200 bg-white hover:border-purple-400 hover:bg-purple-50 transition-colors p-4"
                >
                  <span className="block font-semibold text-gray-800">
                    {r.firstName} {r.lastName}
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
}: {
  selected: StudentResult;
  onYes: () => void;
  onBack: () => void;
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
        <p className="text-sm text-gray-500 mt-2">
          {t('confirmBranch', { branch: selected.branchName })}
        </p>
        {selected.coachName && (
          <p className="text-sm text-gray-500 mt-1">
            {t('confirmCoach', { coach: selected.coachName })}
          </p>
        )}
      </div>
      <button
        type="button"
        onClick={onYes}
        className="mt-6 w-full bg-purple-600 hover:bg-purple-700 rounded-2xl py-4 font-bold uppercase tracking-wide text-white border-b-4 border-purple-800 active:border-b-2 active:translate-y-0.5 transition-all"
      >
        {t('confirmYes')}
      </button>
      <button
        type="button"
        onClick={onBack}
        className="mt-3 w-full rounded-2xl py-3 font-semibold text-gray-500 hover:text-gray-700"
      >
        {t('confirmBack')}
      </button>
    </>
  );
}

function DobStep({
  selected,
  dobDay,
  dobMonth,
  dobYear,
  dayRef,
  monthRef,
  yearRef,
  onDayChange,
  onMonthChange,
  onYearChange,
  dobValid,
  verifying,
  verifyError,
  locked,
  onVerify,
  onBack,
}: {
  selected: StudentResult;
  dobDay: string;
  dobMonth: string;
  dobYear: string;
  dayRef: React.RefObject<HTMLInputElement | null>;
  monthRef: React.RefObject<HTMLInputElement | null>;
  yearRef: React.RefObject<HTMLInputElement | null>;
  onDayChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onMonthChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onYearChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  dobValid: boolean;
  verifying: boolean;
  verifyError: string | null;
  locked: boolean;
  onVerify: () => void;
  onBack: () => void;
}) {
  const t = useTranslations('welcome');
  return (
    <>
      <h1 className="text-2xl font-bold text-gray-800 text-center">
        {t('dobTitle')}
      </h1>
      <p className="text-sm text-gray-500 mt-2 text-center">
        {selected.firstName} {selected.lastName} · {t('dobSubtitle')}
      </p>

      <form
        className="mt-6"
        onSubmit={(e) => {
          e.preventDefault();
          onVerify();
        }}
      >
        <div className="flex gap-2">
          <input
            ref={dayRef}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            aria-label={t('dobDay')}
            placeholder={t('dobDay')}
            value={dobDay}
            onChange={onDayChange}
            disabled={locked}
            maxLength={2}
            className="w-1/4 text-center rounded-2xl border-2 border-gray-200 py-4 text-lg focus:border-purple-500 focus:outline-none disabled:bg-gray-100"
          />
          <input
            ref={monthRef}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            aria-label={t('dobMonth')}
            placeholder={t('dobMonth')}
            value={dobMonth}
            onChange={onMonthChange}
            disabled={locked}
            maxLength={2}
            className="w-1/4 text-center rounded-2xl border-2 border-gray-200 py-4 text-lg focus:border-purple-500 focus:outline-none disabled:bg-gray-100"
          />
          <input
            ref={yearRef}
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            aria-label={t('dobYear')}
            placeholder={t('dobYear')}
            value={dobYear}
            onChange={onYearChange}
            disabled={locked}
            maxLength={4}
            className="w-1/2 text-center rounded-2xl border-2 border-gray-200 py-4 text-lg focus:border-purple-500 focus:outline-none disabled:bg-gray-100"
          />
        </div>

        {verifyError && !locked && (
          <p role="alert" className="text-sm text-red-500 mt-3">
            {verifyError}
          </p>
        )}
        {locked && (
          <p role="alert" className="text-sm text-red-500 mt-3">
            {t('tooManyAttempts')}
          </p>
        )}

        <button
          type="submit"
          disabled={!dobValid || verifying || locked}
          className="mt-6 w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-300 disabled:border-gray-400 rounded-2xl py-4 font-bold uppercase tracking-wide text-white border-b-4 border-purple-800 active:border-b-2 active:translate-y-0.5 transition-all"
        >
          {verifying ? t('verifying') : t('verifyButton')}
        </button>
      </form>

      <button
        type="button"
        onClick={onBack}
        className="mt-3 w-full rounded-2xl py-3 font-semibold text-gray-500 hover:text-gray-700"
      >
        {t('confirmBack')}
      </button>
    </>
  );
}
