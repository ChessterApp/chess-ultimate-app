'use client';

/**
 * "Add family member" flow for the Chess Empire tournaments page.
 *
 * A verified parent links an additional child from here, reusing the same
 * public onboarding endpoints as the welcome page — search → verify → claim —
 * but writing `relationship='child'` (or 'other') instead of the default
 * 'self'. The branch context is recovered from the durable branch-welcome URL
 * the parent's own onboarding stashed (`readBranchWelcomeUrl`); without it we
 * can't scope the search, so the panel explains how to proceed instead.
 *
 * On a successful claim the parent is already signed in, so the member row is
 * written server-side immediately; a `router.refresh()` reloads the page's
 * snapshot so the new child appears in the family bar + picker.
 */
import { useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { readBranchWelcomeUrl } from '@/lib/invite-storage';

interface SearchResult {
  studentId: string;
  firstName: string;
  lastName: string;
  branchName: string;
  type?: 'student' | 'coach';
}

type Relationship = 'child' | 'other';

const DEBOUNCE_MS = 250;
const MIN_QUERY_CHARS = 2;
const MAX_VISIBLE = 8;

/** Recover the branch token from a stored `/welcome/<token>` URL. */
function branchTokenFromUrl(url: string | null): string | null {
  if (!url) return null;
  const m = url.match(/\/welcome\/([^/?#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

export default function AddFamilyMember() {
  const t = useTranslations('ceTournaments');
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [branchToken, setBranchToken] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [relationship, setRelationship] = useState<Relationship>('child');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // Resolve the stored branch token when the panel first opens (localStorage is
  // unavailable during SSR, so this must run client-side).
  useEffect(() => {
    if (!open) return;
    setBranchToken(branchTokenFromUrl(readBranchWelcomeUrl()));
  }, [open]);

  useEffect(() => {
    const h = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(h);
  }, [query]);

  useEffect(() => {
    if (!open || !branchToken || selected) return;
    if (debounced.length < MIN_QUERY_CHARS) {
      setResults(null);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    const url = `/api/chess-empire/students/search?branchToken=${encodeURIComponent(
      branchToken,
    )}&q=${encodeURIComponent(debounced)}`;
    fetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`status_${res.status}`);
        return (await res.json()) as { results: SearchResult[] };
      })
      .then((body) => setResults(body.results ?? []))
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name === 'AbortError') return;
        setResults([]);
      })
      .finally(() => setSearching(false));
    return () => controller.abort();
  }, [debounced, branchToken, open, selected]);

  const reset = useCallback(() => {
    setQuery('');
    setDebounced('');
    setResults(null);
    setSelected(null);
    setRelationship('child');
    setError(null);
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    reset();
    setDone(null);
  }, [reset]);

  const submit = useCallback(async () => {
    if (!selected || !branchToken || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const verifyRes = await fetch('/api/chess-empire/students/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          branchToken,
          studentId: selected.studentId,
          relationship,
        }),
      });
      if (!verifyRes.ok) {
        setError(t('addMemberError'));
        return;
      }
      const body = (await verifyRes.json()) as { inviteJwt?: string };
      if (!body.inviteJwt) {
        setError(t('addMemberError'));
        return;
      }
      // The parent is signed in, so claim server-side right away (same logic as
      // the dashboard poller / welcome flow) to write the linked member row.
      const claimRes = await fetch('/api/chess-empire/link/claim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ inviteJwt: body.inviteJwt }),
      });
      if (!claimRes.ok) {
        setError(t('addMemberError'));
        return;
      }
      const name = `${selected.firstName} ${selected.lastName}`.trim();
      setDone(t('addMemberSuccess', { name }));
      reset();
      setOpen(false);
      router.refresh();
    } catch {
      setError(t('addMemberError'));
    } finally {
      setSubmitting(false);
    }
  }, [selected, branchToken, relationship, submitting, reset, router, t]);

  if (!open) {
    return (
      <div className="afm-root">
        {done && <span className="afm-done">{done}</span>}
        <button
          type="button"
          className="afm-open"
          onClick={() => {
            setDone(null);
            setOpen(true);
          }}
        >
          + {t('addFamilyMember')}
        </button>
        {styles}
      </div>
    );
  }

  const visible = (results ?? []).slice(0, MAX_VISIBLE);

  return (
    <div className="afm-root afm-open-panel">
      <div className="afm-panel">
        <div className="afm-head">
          <span className="afm-title">{t('addMemberTitle')}</span>
          <button
            type="button"
            className="afm-close"
            aria-label={t('addMemberCancel')}
            onClick={close}
          >
            ×
          </button>
        </div>

        {!branchToken ? (
          <p className="afm-hint">{t('addMemberUnavailable')}</p>
        ) : selected ? (
          <div className="afm-confirm">
            <p className="afm-confirm-name">
              {selected.firstName} {selected.lastName}
            </p>
            <div className="afm-rel" role="group" aria-label={t('addMemberTitle')}>
              {(['child', 'other'] as Relationship[]).map((r) => (
                <button
                  key={r}
                  type="button"
                  className={`afm-rel-opt${relationship === r ? ' active' : ''}`}
                  aria-pressed={relationship === r}
                  onClick={() => setRelationship(r)}
                >
                  {t(`relationship.${r}`)}
                </button>
              ))}
            </div>
            {error && <p className="afm-error">{error}</p>}
            <div className="afm-actions">
              <button
                type="button"
                className="afm-submit"
                onClick={submit}
                disabled={submitting}
              >
                {submitting ? t('addMemberSubmitting') : t('addMemberSubmit')}
              </button>
              <button
                type="button"
                className="afm-back"
                onClick={() => {
                  setSelected(null);
                  setError(null);
                }}
                disabled={submitting}
              >
                {t('addMemberBack')}
              </button>
            </div>
          </div>
        ) : (
          <div className="afm-search">
            <input
              type="text"
              autoComplete="off"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t('addMemberSearchPlaceholder')}
              className="afm-input"
              aria-label={t('addMemberSearchPlaceholder')}
            />
            {query.trim().length > 0 && query.trim().length < MIN_QUERY_CHARS && (
              <p className="afm-hint">{t('addMemberHint')}</p>
            )}
            {searching && <p className="afm-hint">{t('addMemberSearching')}</p>}
            {!searching &&
              results !== null &&
              visible.length === 0 &&
              debounced.length >= MIN_QUERY_CHARS && (
                <p className="afm-hint">{t('addMemberNoResults')}</p>
              )}
            {!searching && visible.length > 0 && (
              <ul className="afm-results">
                {visible.map((r) => (
                  <li key={r.studentId}>
                    <button
                      type="button"
                      className="afm-result"
                      onClick={() => {
                        setSelected(r);
                        setError(null);
                      }}
                    >
                      {r.firstName} {r.lastName}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
      {styles}
    </div>
  );
}

const styles = (
  <style jsx>{`
    .afm-root {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .afm-open-panel {
      flex: 1 1 100%;
    }
    .afm-done {
      font-size: 0.82rem;
      color: #047857;
      font-weight: 600;
    }
    .afm-open {
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #2563eb;
      font-weight: 700;
      font-size: 0.82rem;
      padding: 6px 12px;
      border-radius: 999px;
      cursor: pointer;
      white-space: nowrap;
    }
    .afm-open:hover {
      border-color: #2563eb;
      background: #eff6ff;
    }
    .afm-panel {
      width: 100%;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      background: #f8fafc;
      padding: 12px;
    }
    .afm-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 8px;
    }
    .afm-title {
      font-weight: 700;
      color: #1e293b;
      font-size: 0.95rem;
    }
    .afm-close {
      border: none;
      background: transparent;
      color: #94a3b8;
      font-size: 1.25rem;
      line-height: 1;
      cursor: pointer;
    }
    .afm-input {
      width: 100%;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 0.9rem;
    }
    .afm-input:focus {
      outline: none;
      border-color: #3b82f6;
      box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
    }
    .afm-hint {
      font-size: 0.8rem;
      color: #94a3b8;
      margin-top: 8px;
    }
    .afm-error {
      font-size: 0.82rem;
      color: #dc2626;
      margin: 8px 0 0;
    }
    .afm-results {
      list-style: none;
      margin: 8px 0 0;
      padding: 0;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .afm-result {
      width: 100%;
      text-align: left;
      border: 1px solid #e2e8f0;
      background: #fff;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 0.9rem;
      font-weight: 600;
      color: #1e293b;
      cursor: pointer;
    }
    .afm-result:hover {
      border-color: #3b82f6;
      background: #eff6ff;
    }
    .afm-confirm-name {
      font-size: 1.05rem;
      font-weight: 700;
      color: #1e293b;
      margin: 4px 0 10px;
    }
    .afm-rel {
      display: flex;
      gap: 8px;
      margin-bottom: 10px;
    }
    .afm-rel-opt {
      flex: 1 1 0;
      border: 1px solid #cbd5e1;
      background: #fff;
      border-radius: 8px;
      padding: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      color: #475569;
      cursor: pointer;
    }
    .afm-rel-opt.active {
      border-color: #2563eb;
      background: #eff6ff;
      color: #2563eb;
    }
    .afm-actions {
      display: flex;
      gap: 8px;
    }
    .afm-submit {
      flex: 1 1 auto;
      border: none;
      background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
      color: #fff;
      font-weight: 700;
      font-size: 0.9rem;
      border-radius: 8px;
      padding: 10px;
      cursor: pointer;
    }
    .afm-submit:disabled {
      background: #e2e8f0;
      color: #94a3b8;
      cursor: not-allowed;
    }
    .afm-back {
      border: 1px solid #cbd5e1;
      background: #fff;
      color: #475569;
      font-weight: 600;
      font-size: 0.85rem;
      border-radius: 8px;
      padding: 10px 14px;
      cursor: pointer;
    }
    .afm-back:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
  `}</style>
);
