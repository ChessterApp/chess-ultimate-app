'use client';

/* Hallmark · pre-emit critique: P5 H4 E5 S4 R5 V4 */

/**
 * "Добавить члена семьи" — rendered as a Clerk `<UserButton.UserProfilePage>`
 * sub-view inside the profile avatar menu (Navbar wires it in). Clerk supplies
 * the account header and back arrow; this component owns the panel below it:
 *
 *  1. Branch chip — «📍 Филиал: <branchName>» — the caller's own branch, pulled
 *     from the authenticated, branch-scoped search endpoint (never a public
 *     token). Shown prominently because the branch is the whole scope.
 *  2. Search — «Поиск по имени», 300 ms debounced, queries only the caller's
 *     own branch via `GET /api/chess-empire/link/search`.
 *  3. Results — same-branch members, each an «Добавить» that links instantly via
 *     `POST /api/chess-empire/link/link-existing`. Empty → «Никого не найдено».
 *  4. Cross-branch fallback — «Другой филиал? Пригласите по эл. почте →» opens
 *     the email-consent form backed by `POST /api/chess-empire/link/invite`.
 *
 * The branch chip + `branchToken` (needed by link-existing) come back on the
 * first, empty-query fetch, so the chip is present before the parent types.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface SearchResult {
  studentId: string;
  firstName: string;
  lastName: string;
  branchName: string;
  type?: 'student' | 'coach';
  /** Already has a member row in this org (self-registered or linked elsewhere). */
  alreadyLinked?: boolean;
  /** The existing member row belongs to the caller themselves. */
  ownedBySelf?: boolean;
}

interface SearchResponse {
  results: SearchResult[];
  branchName: string | null;
  branchToken: string | null;
}

const DEBOUNCE_MS = 300;
const MIN_QUERY_CHARS = 2;
const SEARCH_URL = '/api/chess-empire/link/search';

export default function AddFamilyMember() {
  const [branchName, setBranchName] = useState<string | null>(null);
  const [branchToken, setBranchToken] = useState<string | null>(null);

  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [addingId, setAddingId] = useState<string | null>(null);
  const [addedIds, setAddedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);

  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteName, setInviteName] = useState('');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteSending, setInviteSending] = useState(false);
  const [inviteSent, setInviteSent] = useState(false);

  // First load: empty-query fetch resolves the branch chip + link token before
  // the parent types a single character.
  useEffect(() => {
    let cancelled = false;
    fetch(`${SEARCH_URL}?q=`)
      .then((res) => (res.ok ? (res.json() as Promise<SearchResponse>) : null))
      .then((body) => {
        if (cancelled || !body) return;
        setBranchName(body.branchName);
        setBranchToken(body.branchToken);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const h = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(h);
  }, [query]);

  useEffect(() => {
    if (debounced.length < MIN_QUERY_CHARS) {
      setResults(null);
      setSearching(false);
      return;
    }
    const controller = new AbortController();
    setSearching(true);
    fetch(`${SEARCH_URL}?q=${encodeURIComponent(debounced)}`, {
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`status_${res.status}`);
        return (await res.json()) as SearchResponse;
      })
      .then((body) => {
        setResults(body.results ?? []);
        if (body.branchName) setBranchName(body.branchName);
        if (body.branchToken) setBranchToken(body.branchToken);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string })?.name === 'AbortError') return;
        setResults([]);
      })
      .finally(() => setSearching(false));
    return () => controller.abort();
  }, [debounced]);

  const addMember = useCallback(
    async (member: SearchResult) => {
      if (!branchToken || addingId) return;
      setAddingId(member.studentId);
      setError(null);
      try {
        const res = await fetch('/api/chess-empire/link/link-existing', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            branchToken,
            studentId: member.studentId,
            relationship: 'child',
          }),
        });
        if (!res.ok) {
          setError('Не удалось добавить. Попробуйте ещё раз.');
          return;
        }
        setAddedIds((prev) => new Set(prev).add(member.studentId));
      } catch {
        setError('Не удалось добавить. Попробуйте ещё раз.');
      } finally {
        setAddingId(null);
      }
    },
    [branchToken, addingId],
  );

  const sendInvite = useCallback(async () => {
    const name = inviteName.trim();
    const email = inviteEmail.trim();
    if ((!name && !email) || inviteSending) return;
    setInviteSending(true);
    setError(null);
    try {
      const res = await fetch('/api/chess-empire/link/invite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name || undefined,
          email: email || undefined,
          relationship: 'child',
        }),
      });
      if (!res.ok) {
        setError('Не удалось отправить приглашение.');
        return;
      }
      setInviteSent(true);
      setInviteName('');
      setInviteEmail('');
    } catch {
      setError('Не удалось отправить приглашение.');
    } finally {
      setInviteSending(false);
    }
  }, [inviteName, inviteEmail, inviteSending]);

  const searchRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    searchRef.current?.focus();
  }, []);

  const visible = results ?? [];
  const noMatches =
    !searching && results !== null && visible.length === 0 && debounced.length >= MIN_QUERY_CHARS;

  return (
    <div className="afm">
      <header className="afm-head">
        <span className="afm-chip" title={branchName ?? undefined}>
          <span aria-hidden>📍</span> Филиал: <b>{branchName ?? '—'}</b>
        </span>
      </header>

      <label className="afm-field">
        <span className="afm-vh">Поиск по имени</span>
        <input
          ref={searchRef}
          type="text"
          autoComplete="off"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Поиск по имени"
          className="afm-input"
          aria-label="Поиск по имени"
        />
      </label>

      {query.trim().length > 0 && query.trim().length < MIN_QUERY_CHARS && (
        <p className="afm-hint">Введите ещё пару букв…</p>
      )}
      {searching && <p className="afm-hint">Поиск…</p>}
      {noMatches && <p className="afm-empty">Никого не найдено в вашем филиале</p>}
      {error && <p className="afm-error" role="alert">{error}</p>}

      {visible.length > 0 && (
        <ul className="afm-list">
          {visible.map((m) => {
            const added = addedIds.has(m.studentId);
            const busy = addingId === m.studentId;
            // A student the caller already owns is shown as "already yours"
            // (disabled). Anyone else — including a foreign-owned, already-linked
            // student (added via an auto-accept edge) — stays addable.
            const ownedBySelf = m.ownedBySelf === true;
            const label = ownedBySelf
              ? '✓ Уже добавлен'
              : added
                ? '✓ Добавлен'
                : busy
                  ? 'Добавляем…'
                  : 'Добавить';
            return (
              <li key={m.studentId} className="afm-row">
                <span className="afm-person">
                  <span className="afm-name">
                    {m.firstName} {m.lastName}
                  </span>
                  <span className="afm-branch">{m.branchName}</span>
                </span>
                <button
                  type="button"
                  className="afm-add"
                  onClick={() => addMember(m)}
                  disabled={added || busy || ownedBySelf || !branchToken}
                  data-state={
                    added || ownedBySelf ? 'done' : busy ? 'loading' : 'idle'
                  }
                >
                  {label}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      <footer className="afm-foot">
        {!inviteOpen ? (
          <button
            type="button"
            className="afm-invite-link"
            onClick={() => {
              setInviteOpen(true);
              setError(null);
              setInviteSent(false);
            }}
          >
            Другой филиал? Пригласите по эл. почте →
          </button>
        ) : inviteSent ? (
          <p className="afm-sent">Приглашение отправлено ✓</p>
        ) : (
          <div className="afm-invite">
            <input
              type="text"
              autoComplete="off"
              value={inviteName}
              onChange={(e) => setInviteName(e.target.value)}
              placeholder="Имя"
              className="afm-input"
              aria-label="Имя"
            />
            <input
              type="email"
              autoComplete="off"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
              placeholder="Эл. почта"
              className="afm-input"
              aria-label="Эл. почта"
            />
            <div className="afm-invite-actions">
              <button
                type="button"
                className="afm-add afm-add-primary"
                onClick={sendInvite}
                disabled={inviteSending || (!inviteName.trim() && !inviteEmail.trim())}
                data-state={inviteSending ? 'loading' : 'idle'}
              >
                {inviteSending ? 'Отправляем…' : 'Отправить приглашение'}
              </button>
              <button
                type="button"
                className="afm-ghost"
                onClick={() => setInviteOpen(false)}
                disabled={inviteSending}
              >
                Отмена
              </button>
            </div>
          </div>
        )}
      </footer>

      <style jsx>{`
        .afm {
          --afm-accent: #7c3aed;
          --afm-accent-strong: #6d28d9;
          --afm-ink: #1e2330;
          --afm-muted: #6b7280;
          --afm-line: #e6e5ee;
          --afm-surface: #ffffff;
          --afm-raised: #f7f6fb;
          display: flex;
          flex-direction: column;
          gap: 14px;
          padding: 4px 2px 8px;
          color: var(--afm-ink);
          font-size: 0.9rem;
        }
        .afm-head {
          display: flex;
        }
        .afm-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          max-width: 100%;
          padding: 6px 12px;
          border-radius: 999px;
          background: var(--afm-raised);
          border: 1px solid var(--afm-line);
          color: var(--afm-muted);
          font-size: 0.82rem;
          font-weight: 500;
          overflow: hidden;
          white-space: nowrap;
          text-overflow: ellipsis;
        }
        .afm-chip b {
          color: var(--afm-ink);
          font-weight: 700;
        }
        .afm-field {
          display: block;
        }
        .afm-vh {
          position: absolute;
          width: 1px;
          height: 1px;
          overflow: hidden;
          clip: rect(0 0 0 0);
          white-space: nowrap;
        }
        .afm-input {
          width: 100%;
          box-sizing: border-box;
          border: 1px solid var(--afm-line);
          border-radius: 10px;
          padding: 11px 13px;
          font-size: 0.9rem;
          color: var(--afm-ink);
          background: var(--afm-surface);
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }
        .afm-input::placeholder {
          color: #9aa0ac;
        }
        .afm-input:hover {
          border-color: #d3d1e0;
        }
        .afm-input:focus-visible,
        .afm-input:focus {
          outline: none;
          border-color: var(--afm-accent);
          box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.16);
        }
        .afm-hint {
          margin: 0;
          font-size: 0.8rem;
          color: var(--afm-muted);
        }
        .afm-empty {
          margin: 0;
          font-size: 0.85rem;
          color: var(--afm-muted);
          padding: 10px 12px;
          background: var(--afm-raised);
          border-radius: 10px;
        }
        .afm-error {
          margin: 0;
          font-size: 0.82rem;
          color: #b91c1c;
        }
        .afm-list {
          list-style: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .afm-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          min-width: 0;
          padding: 10px 12px;
          border: 1px solid var(--afm-line);
          border-radius: 10px;
          background: var(--afm-surface);
        }
        .afm-person {
          display: flex;
          flex-direction: column;
          gap: 2px;
          min-width: 0;
        }
        .afm-name {
          font-weight: 600;
          color: var(--afm-ink);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .afm-branch {
          font-size: 0.74rem;
          color: var(--afm-muted);
        }
        .afm-add {
          flex: 0 0 auto;
          border: 1px solid var(--afm-accent);
          background: var(--afm-accent);
          color: #fff;
          font-weight: 600;
          font-size: 0.82rem;
          padding: 8px 14px;
          border-radius: 8px;
          cursor: pointer;
          transition: background 0.15s ease, border-color 0.15s ease,
            transform 0.05s ease;
        }
        .afm-add:hover {
          background: var(--afm-accent-strong);
          border-color: var(--afm-accent-strong);
        }
        .afm-add:focus-visible {
          outline: none;
          box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.3);
        }
        .afm-add:active {
          transform: translateY(1px);
        }
        .afm-add:disabled {
          cursor: default;
          transform: none;
        }
        .afm-add[data-state='done'] {
          background: #ecfdf3;
          border-color: #b7f0cd;
          color: #067647;
        }
        .afm-add[data-state='loading'] {
          background: var(--afm-raised);
          border-color: var(--afm-line);
          color: var(--afm-muted);
        }
        .afm-foot {
          border-top: 1px solid var(--afm-line);
          padding-top: 12px;
        }
        .afm-invite-link {
          border: none;
          background: transparent;
          color: var(--afm-accent);
          font-size: 0.84rem;
          font-weight: 600;
          padding: 4px 0;
          cursor: pointer;
          text-align: left;
        }
        .afm-invite-link:hover {
          color: var(--afm-accent-strong);
          text-decoration: underline;
        }
        .afm-invite-link:focus-visible {
          outline: 2px solid rgba(124, 58, 237, 0.4);
          outline-offset: 2px;
          border-radius: 4px;
        }
        .afm-invite {
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .afm-invite-actions {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
        }
        .afm-add-primary {
          flex: 1 1 auto;
          padding: 10px 14px;
        }
        .afm-ghost {
          border: 1px solid var(--afm-line);
          background: var(--afm-surface);
          color: var(--afm-muted);
          font-weight: 600;
          font-size: 0.82rem;
          padding: 10px 14px;
          border-radius: 8px;
          cursor: pointer;
        }
        .afm-ghost:hover {
          border-color: #d3d1e0;
          color: var(--afm-ink);
        }
        .afm-ghost:disabled {
          opacity: 0.5;
          cursor: default;
        }
        .afm-sent {
          margin: 0;
          font-size: 0.85rem;
          font-weight: 600;
          color: #067647;
        }
      `}</style>
    </div>
  );
}
