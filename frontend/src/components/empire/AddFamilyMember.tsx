'use client';

/**
 * Universal "Add family member" flow.
 *
 * Surfaced three ways — inline on the tournaments page and profile (its own
 * trigger button) and as a modal from the Chess Empire navbar avatar dropdown
 * (controlled via `open`/`onClose` with `asModal`). One members fetch when the
 * panel opens decides the fork on the primary member's onboarding source:
 *
 *  - **branch** — roster search within the parent's own branch via the
 *    AUTHENTICATED `/api/chess-empire/link/search` route (branch resolved from
 *    the session, not a public token). Selecting a student links INSTANTLY via
 *    `/api/chess-empire/link/link-existing` — no email, no accept step. A
 *    "different branch?" toggle switches to the email-invite form for someone
 *    outside the branch. A `branchToken` (from the stashed branch-welcome URL or
 *    the server response) is OPTIONAL — passed through for back-compat when
 *    present, but the link no longer depends on one existing.
 *  - **online** — an online account has no roster, so it goes straight to the
 *    email-invite form.
 *
 * The email-invite path (`/api/chess-empire/link/invite`) never mints a
 * placeholder person: it emails the target a consent link and the reciprocal
 * family edge only forms once they accept.
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
type AddMode = 'branch' | 'online';

interface MemberRow {
  relationship: 'self' | 'child' | 'other';
  source?: 'chess_empire' | 'online';
}

interface AddFamilyMemberProps {
  /** When provided, the panel is controlled (used by the navbar modal). */
  open?: boolean;
  /** Requested close in controlled mode. */
  onClose?: () => void;
  /** Render the open panel as a centered modal overlay instead of inline. */
  asModal?: boolean;
}

const DEBOUNCE_MS = 250;
const MIN_QUERY_CHARS = 2;
const MAX_VISIBLE = 8;

/** Recover the branch token from a stored `/welcome/<token>` URL. */
function branchTokenFromUrl(url: string | null): string | null {
  if (!url) return null;
  const m = url.match(/\/welcome\/([^/?#]+)/);
  return m ? decodeURIComponent(m[1]) : null;
}

/**
 * The primary member's onboarding source decides the add-mode: 'self' wins, else
 * the first member (mirrors `pickPrimaryState`). Defaults to branch mode when
 * unknown so a failed/empty lookup keeps today's roster-search behaviour.
 */
function pickMode(members: MemberRow[]): AddMode {
  const primary = members.find((m) => m.relationship === 'self') ?? members[0];
  return primary?.source === 'online' ? 'online' : 'branch';
}

export default function AddFamilyMember({
  open: controlledOpen,
  onClose,
  asModal = false,
}: AddFamilyMemberProps = {}) {
  const t = useTranslations('ceTournaments');
  const router = useRouter();
  const isControlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const open = isControlled ? controlledOpen : internalOpen;

  const [mode, setMode] = useState<AddMode | null>(null);
  const [branchToken, setBranchToken] = useState<string | null>(null);
  const [branchResolved, setBranchResolved] = useState(false);
  // The members lookup itself failed (not merely "no public token"): the only
  // case that now falls back to the addMemberUnavailable copy.
  const [lookupFailed, setLookupFailed] = useState(false);
  const [inviteMode, setInviteMode] = useState(false);
  const [inviteName, setInviteName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [selected, setSelected] = useState<SearchResult | null>(null);
  const [relationship, setRelationship] = useState<Relationship>('child');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // Resolve the add-mode when the panel first opens. One members fetch decides
  // the fork: an online primary → invite form; otherwise branch mode, whose
  // roster search runs against the authenticated `link/search` route (branch
  // derived from the session). An OPTIONAL branchToken — the stashed
  // branch-welcome URL (fast path) or the server-resolved `branchToken` — is
  // carried through for the back-compat link path when present. Only a failed
  // lookup (network/HTTP error) falls back to the "unavailable" copy.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setBranchResolved(false);
    setLookupFailed(false);
    fetch('/api/chess-empire/link/members')
      .then((res) => {
        if (!res.ok) throw new Error(`status_${res.status}`);
        return res.json() as Promise<{
          members?: MemberRow[];
          branchToken?: string | null;
        }>;
      })
      .then((body) => {
        if (cancelled) return;
        const nextMode = pickMode(body?.members ?? []);
        setMode(nextMode);
        if (nextMode === 'branch') {
          const fast = branchTokenFromUrl(readBranchWelcomeUrl());
          setBranchToken(fast ?? body?.branchToken ?? null);
        }
        setBranchResolved(true);
      })
      .catch(() => {
        if (cancelled) return;
        setLookupFailed(true);
        setBranchResolved(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  useEffect(() => {
    const h = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(h);
  }, [query]);

  useEffect(() => {
    if (!open || mode !== 'branch' || selected || inviteMode) return;
    if (debounced.length < MIN_QUERY_CHARS) {
      setResults(null);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    // Authenticated, branch-scoped search — the branch is resolved from the
    // session server-side, so no public token is needed to search.
    const url = `/api/chess-empire/link/search?q=${encodeURIComponent(
      debounced,
    )}`;
    fetch(url, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(`status_${res.status}`);
        return (await res.json()) as {
          results: SearchResult[];
          branchToken?: string | null;
        };
      })
      .then((body) => {
        setResults(body.results ?? []);
        // Opportunistically capture a server-resolved token for the back-compat
        // link path; the link works without one either way.
        if (body.branchToken) setBranchToken(body.branchToken);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name === 'AbortError') return;
        setResults([]);
      })
      .finally(() => setSearching(false));
    return () => controller.abort();
  }, [debounced, mode, open, selected, inviteMode]);

  const reset = useCallback(() => {
    setQuery('');
    setDebounced('');
    setResults(null);
    setSelected(null);
    setRelationship('child');
    setInviteMode(false);
    setInviteName('');
    setInviteEmail('');
    setError(null);
  }, []);

  const openPanel = useCallback(() => {
    setDone(null);
    if (!isControlled) setInternalOpen(true);
  }, [isControlled]);

  const close = useCallback(() => {
    reset();
    setMode(null);
    setBranchResolved(false);
    setLookupFailed(false);
    if (isControlled) onClose?.();
    else setInternalOpen(false);
  }, [reset, isControlled, onClose]);

  // Same-branch instant link: the roster pick forms the verified member row in
  // one server call, no email or accept step.
  const submitBranch = useCallback(async () => {
    if (!selected || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch('/api/chess-empire/link/link-existing', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          // Token is optional now — send it only for the back-compat path.
          ...(branchToken ? { branchToken } : {}),
          studentId: selected.studentId,
          relationship,
        }),
      });
      if (!res.ok) {
        setError(t('addMemberError'));
        return;
      }
      const name = `${selected.firstName} ${selected.lastName}`.trim();
      setDone(t('addMemberSuccess', { name }));
      reset();
      close();
      router.refresh();
    } catch {
      setError(t('addMemberError'));
    } finally {
      setSubmitting(false);
    }
  }, [selected, branchToken, relationship, submitting, reset, close, router, t]);

  // Cross-branch / online→branch: no roster to search. Email the target a
  // consent link — the family edge forms only when they accept.
  const submitInvite = useCallback(async () => {
    const name = inviteName.trim();
    const email = inviteEmail.trim();
    if ((!name && !email) || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch('/api/chess-empire/link/invite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name || undefined,
          email: email || undefined,
          relationship,
        }),
      });
      if (!res.ok) {
        setError(t('addMemberError'));
        return;
      }
      setDone(t('addMemberInviteSent'));
      reset();
      close();
    } catch {
      setError(t('addMemberError'));
    } finally {
      setSubmitting(false);
    }
  }, [inviteName, inviteEmail, relationship, submitting, reset, close, t]);

  const relationshipPicker = (
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
  );

  if (!open) {
    // Modal mode renders nothing while closed — the navbar owns the trigger.
    if (asModal) return null;
    return (
      <div className="afm-root">
        {done && <span className="afm-done">{done}</span>}
        <button type="button" className="afm-open" onClick={openPanel}>
          + {t('addFamilyMember')}
        </button>
        {styles}
      </div>
    );
  }

  const visible = (results ?? []).slice(0, MAX_VISIBLE);
  const showInvite = mode === 'online' || inviteMode;

  const inviteForm = (
    <div className="afm-confirm">
      <p className="afm-hint afm-online-sub">{t('addMemberInviteSubtitle')}</p>
      <input
        type="text"
        autoComplete="off"
        value={inviteName}
        onChange={(e) => setInviteName(e.target.value)}
        placeholder={t('addMemberNamePlaceholder')}
        className="afm-input"
        aria-label={t('addMemberNamePlaceholder')}
      />
      <input
        type="email"
        autoComplete="off"
        value={inviteEmail}
        onChange={(e) => setInviteEmail(e.target.value)}
        placeholder={t('addMemberInviteEmailPlaceholder')}
        className="afm-input afm-input-stacked"
        aria-label={t('addMemberInviteEmailPlaceholder')}
      />
      {relationshipPicker}
      {error && <p className="afm-error">{error}</p>}
      <div className="afm-actions">
        <button
          type="button"
          className="afm-submit"
          onClick={submitInvite}
          disabled={submitting || (!inviteName.trim() && !inviteEmail.trim())}
        >
          {submitting
            ? t('addMemberInviteSubmitting')
            : t('addMemberInviteSubmit')}
        </button>
        {mode === 'branch' && (
          <button
            type="button"
            className="afm-back"
            onClick={() => {
              setInviteMode(false);
              setError(null);
            }}
            disabled={submitting}
          >
            {t('addMemberInviteBackToSearch')}
          </button>
        )}
      </div>
    </div>
  );

  const body = !branchResolved ? (
    <p className="afm-hint">{t('addMemberResolving')}</p>
  ) : showInvite ? (
    inviteForm
  ) : lookupFailed ? (
    <div>
      <p className="afm-hint">{t('addMemberUnavailable')}</p>
      <div className="afm-actions">
        <button
          type="button"
          className="afm-back"
          onClick={() => setInviteMode(true)}
        >
          {t('addMemberInviteToggle')}
        </button>
      </div>
    </div>
  ) : selected ? (
    <div className="afm-confirm">
      <p className="afm-confirm-name">
        {selected.firstName} {selected.lastName}
      </p>
      {relationshipPicker}
      {error && <p className="afm-error">{error}</p>}
      <div className="afm-actions">
        <button
          type="button"
          className="afm-submit"
          onClick={submitBranch}
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
      <button
        type="button"
        className="afm-invite-toggle"
        onClick={() => {
          setInviteMode(true);
          setError(null);
        }}
      >
        {t('addMemberInviteToggle')}
      </button>
    </div>
  );

  const panel = (
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
      {body}
    </div>
  );

  if (asModal) {
    return (
      <div
        className="afm-overlay"
        role="dialog"
        aria-modal="true"
        aria-label={t('addMemberTitle')}
        onClick={(e) => {
          if (e.target === e.currentTarget) close();
        }}
      >
        <div className="afm-modal">{panel}</div>
        {styles}
      </div>
    );
  }

  return (
    <div className="afm-root afm-open-panel">
      {panel}
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
    .afm-overlay {
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: rgba(15, 23, 42, 0.45);
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding: 72px 16px 16px;
    }
    .afm-modal {
      width: 100%;
      max-width: 420px;
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
    .afm-input-stacked {
      margin-top: 8px;
      margin-bottom: 10px;
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
    .afm-online-sub {
      margin-top: 0;
      margin-bottom: 10px;
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
    .afm-invite-toggle {
      margin-top: 10px;
      border: none;
      background: transparent;
      color: #2563eb;
      font-size: 0.82rem;
      font-weight: 600;
      cursor: pointer;
      padding: 4px 0;
      text-align: left;
    }
    .afm-invite-toggle:hover {
      text-decoration: underline;
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
