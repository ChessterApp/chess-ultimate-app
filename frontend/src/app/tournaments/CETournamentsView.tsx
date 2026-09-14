'use client';

/**
 * Chess Empire tournaments — client view + one-click registration.
 *
 * A faithful port of the vanilla public schedule
 * (chess-empire-database/tournaments.{html,js}): a branch accordion with
 * upcoming-tournament counts, per-tournament detail panels (date/time, format,
 * fee, rounds, capacity meter, full-name roster, flip-clock countdown), and a
 * Register button with open / closed / full states.
 *
 * The ONE functional difference from the vanilla page: a signed-in verified
 * member registers with a single click — optimistic ✅, their name lands in the
 * roster immediately, confirmed server-side (student resolved from the member,
 * never a search). Logged-out / unverified visitors see the identical UI; a
 * click prompts sign-in / verification. Tournament data + rosters poll every
 * 15s to mirror the vanilla page's realtime feel.
 */
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import Link from 'next/link';
import { useTranslations, useLocale } from 'next-intl';

export type { CETournamentCard, CEBranchRef } from '@/lib/ce-tournaments-data';
import type {
  CETournamentCard,
  CEBranchRef,
} from '@/lib/ce-tournaments-data';

export type CEViewer =
  | { state: 'logged_out' }
  | { state: 'unverified' }
  | { state: 'verified'; studentName: string | null };

const SIGN_IN_HREF = '/sign-in?redirect_url=/tournaments';
const VERIFY_HREF = '/dashboard';
const POLL_INTERVAL_MS = 15000;

/** App locale → BCP-47 tag for Intl date/number formatting. */
const LOCALE_TAG: Record<string, string> = {
  en: 'en-US',
  ru: 'ru-RU',
  kz: 'kk-KZ',
};

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------
function formatDate(iso: string, tag: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(tag, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

function formatTime(t: string | null): string {
  if (!t) return '—';
  return String(t).slice(0, 5);
}

function formatDeadline(iso: string, tag: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(tag, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatFee(fee: number, tag: string, freeLabel: string): string {
  const n = Number(fee || 0);
  if (n === 0) return freeLabel;
  return `${n.toLocaleString(tag)} ₸`;
}

function deadlinePassed(card: CETournamentCard, now: number): boolean {
  if (!card.registration_deadline) return false;
  const ms = Date.parse(card.registration_deadline);
  if (Number.isNaN(ms)) return false;
  return now > ms;
}

/** Registration is unavailable: not open, at capacity, or past its deadline. */
function isClosed(card: CETournamentCard, now: number): boolean {
  const full = card.registered_count >= card.capacity;
  return card.status !== 'open' || full || deadlinePassed(card, now);
}

/**
 * A Titled ("Разрядники") tournament: CE league `'R'`. The schedule payload
 * doesn't carry the league letter client-side, so this is detected from the
 * localized tournament name — no new API field is introduced for it.
 */
function isRazryadOnly(card: CETournamentCard): boolean {
  return /Турнир\s+Разрядник/i.test(card.name);
}

function pad2(n: number): string {
  return String(Math.max(0, n)).padStart(2, '0');
}

function countdownParts(ms: number) {
  const totalSec = Math.floor(Math.max(0, ms) / 1000);
  return {
    days: pad2(Math.floor(totalSec / 86400)),
    hours: pad2(Math.floor((totalSec % 86400) / 3600)),
    minutes: pad2(Math.floor((totalSec % 3600) / 60)),
    seconds: pad2(totalSec % 60),
  };
}

/** Amber under 3h, red + pulse under 1h — mirrors the vanilla urgency classes. */
function urgencyClass(ms: number): string {
  if (ms < 60 * 60 * 1000) return 'critical';
  if (ms < 3 * 60 * 60 * 1000) return 'urgent';
  return '';
}

// ---------------------------------------------------------------------------
// Countdown (flip-clock)
// ---------------------------------------------------------------------------
function Countdown({ deadline }: { deadline: string }) {
  const t = useTranslations('ceTournaments');
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  const target = Date.parse(deadline);
  if (Number.isNaN(target)) return null;
  const ms = target - now;
  if (ms <= 0) return null;
  const parts = countdownParts(ms);
  const urgency = urgencyClass(ms);

  const cards: Array<[keyof typeof parts, string]> = [
    ['days', t('countdown.days')],
    ['hours', t('countdown.hours')],
    ['minutes', t('countdown.minutes')],
    ['seconds', t('countdown.seconds')],
  ];

  return (
    <div className={`countdown-block ${urgency}`}>
      <div className="countdown-label">{t('countdown.label')}</div>
      <div className="countdown-cards">
        {cards.map(([unit, label]) => (
          <div className="countdown-card" key={unit}>
            <div className="countdown-number">{parts[unit]}</div>
            <span className="countdown-unit">{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tournament panel
// ---------------------------------------------------------------------------
interface PanelFeedback {
  error?: string | null;
  notice?: string | null;
  busy?: boolean;
}

function TournamentPanel({
  card,
  viewer,
  feedback,
  highlighted,
  panelRef,
  onRegister,
  onCancel,
}: {
  card: CETournamentCard;
  viewer: CEViewer;
  feedback: PanelFeedback;
  highlighted: boolean;
  panelRef: (el: HTMLDivElement | null) => void;
  onRegister: (card: CETournamentCard) => void;
  onCancel: (card: CETournamentCard) => void;
}) {
  const t = useTranslations('ceTournaments');
  const locale = useLocale();
  const tag = LOCALE_TAG[locale] ?? 'en-US';

  // Only tournaments with a deadline need a live clock (to flip to the closed
  // state when it passes). Without one, `now` stays fixed from first paint.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!card.registration_deadline) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [card.registration_deadline]);

  const full = card.registered_count >= card.capacity;
  const closed = isClosed(card, now);
  const registered = card.registration_id !== null;
  const busy = feedback.busy ?? false;

  const fillPct = Math.min(
    100,
    Math.round((card.registered_count / Math.max(1, card.capacity)) * 100),
  );
  const fillClass = fillPct >= 100 ? 'full' : fillPct >= 75 ? 'warn' : '';

  const closesLabel =
    card.registration_deadline && !deadlinePassed(card, now)
      ? t('closesAt', { datetime: formatDeadline(card.registration_deadline, tag) })
      : null;

  return (
    <div
      ref={panelRef}
      className={`tournament-row expanded${highlighted ? ' highlighted' : ''}`}
      data-tournament-id={card.id}
    >
      <div className="tournament-summary">
        <div>
          <div className="tournament-title">{card.name}</div>
          {isRazryadOnly(card) && (
            <span className="razryad-badge">{t('razryadOnly')}</span>
          )}
          <div className="tournament-meta" style={{ marginTop: 4 }}>
            <span>{formatDate(card.tournament_date, tag)}</span>
            <span>·</span>
            <span>{t('startAt', { time: formatTime(card.start_time) })}</span>
            {closesLabel && (
              <>
                <span>·</span>
                <span>{closesLabel}</span>
              </>
            )}
          </div>
        </div>
        <div className="tournament-meta">
          <span className={`pill${closed || full ? ' full' : ''}`}>
            {card.registered_count}/{card.capacity}
          </span>
        </div>
      </div>

      <div className="tournament-detail">
        <div className="detail-inner">
          {card.info && <div className="info-box">{card.info}</div>}

          <div className="detail-grid">
            <DetailItem label={t('date')} value={formatDate(card.tournament_date, tag)} />
            <DetailItem label={t('time')} value={formatTime(card.start_time)} />
            <DetailItem label={t('format')} value={card.time_format || '—'} />
            <DetailItem
              label={t('entryFee')}
              value={formatFee(card.registration_fee, tag, t('free'))}
            />
            <DetailItem label={t('rounds')} value={String(card.rounds)} />
            <div className="detail-item">
              <div className="label">{t('capacityLabel')}</div>
              <div className="value">
                {card.registered_count}/{card.capacity}
              </div>
              <div className="capacity-bar">
                <div
                  className={`capacity-fill ${fillClass}`}
                  style={{ width: `${fillPct}%` }}
                />
              </div>
            </div>
          </div>

          <div className="detail-item" style={{ marginBottom: 8 }}>
            <div className="label">{t('rosterLabel')}</div>
          </div>
          <div className="roster">
            {card.roster.length === 0 ? (
              <div className="roster-empty">{t('rosterEmpty')}</div>
            ) : (
              <div className="roster-list">
                {card.roster.map((name, i) => (
                  <div className="roster-item" key={`${name}-${i}`}>
                    <span className="roster-num">{i + 1}.</span>
                    <span>{name}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {!closed && card.registration_deadline && (
            <Countdown deadline={card.registration_deadline} />
          )}

          {registered ? (
            <div className="registered-row">
              <span className="registered-label">{t('registered')}</span>
              <button
                type="button"
                className="cancel-btn"
                onClick={() => onCancel(card)}
                disabled={busy}
              >
                {busy ? t('cancelling') : t('cancelRegistration')}
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="register-btn"
              onClick={() => onRegister(card)}
              disabled={busy || closed}
            >
              {busy
                ? t('registering')
                : closed
                  ? full
                    ? t('tournamentFull')
                    : t('registrationClosed')
                  : t('register')}
            </button>
          )}

          {feedback.notice && !registered && (
            <div className="register-note register-notice">
              <p>{feedback.notice}</p>
              {viewer.state === 'logged_out' && (
                <Link href={SIGN_IN_HREF} className="notice-link">
                  {t('signInToRegister')} →
                </Link>
              )}
              {viewer.state === 'unverified' && (
                <Link href={VERIFY_HREF} className="notice-link">
                  {t('verifyMembership')} →
                </Link>
              )}
            </div>
          )}

          {feedback.error && <p className="register-error">{feedback.error}</p>}
        </div>
      </div>
    </div>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="detail-item">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Branch card (accordion)
// ---------------------------------------------------------------------------
function BranchCard({
  branch,
  tournaments,
  expanded,
  onToggle,
  viewer,
  feedbackById,
  highlightId,
  registerPanelRef,
  onRegister,
  onCancel,
}: {
  branch: CEBranchRef;
  tournaments: CETournamentCard[];
  expanded: boolean;
  onToggle: () => void;
  viewer: CEViewer;
  feedbackById: Record<string, PanelFeedback>;
  highlightId: string | null;
  registerPanelRef: (id: string, el: HTMLDivElement | null) => void;
  onRegister: (card: CETournamentCard) => void;
  onCancel: (card: CETournamentCard) => void;
}) {
  const t = useTranslations('ceTournaments');
  const branchName = t.has(`branchNames.${branch.name}`)
    ? t(`branchNames.${branch.name}`)
    : branch.name;
  const count = tournaments.length;

  return (
    <div className={`branch-card${expanded ? ' expanded' : ''}`}>
      <div
        className="branch-header"
        role="button"
        tabIndex={0}
        aria-expanded={expanded}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        <div className="branch-name">{branchName}</div>
        <div className="branch-header-right">
          <span className={`count-badge${count === 0 ? ' zero' : ''}`}>
            {count > 0 ? t('upcoming', { count }) : t('noUpcoming')}
          </span>
          <svg
            className="branch-chevron"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            aria-hidden="true"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </div>
      {expanded && (
        <div className="branch-body">
          <div className="tournaments-list">
            {count === 0 ? (
              <div className="empty-row">{t('noUpcoming')}</div>
            ) : (
              tournaments.map((card) => (
                <TournamentPanel
                  key={card.id}
                  card={card}
                  viewer={viewer}
                  feedback={feedbackById[card.id] ?? {}}
                  highlighted={highlightId === card.id}
                  panelRef={(el) => registerPanelRef(card.id, el)}
                  onRegister={onRegister}
                  onCancel={onCancel}
                />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root view
// ---------------------------------------------------------------------------
export default function CETournamentsView({
  tournaments,
  branches,
  viewer,
  deepLinkTournamentId = null,
}: {
  tournaments: CETournamentCard[];
  branches?: CEBranchRef[];
  viewer: CEViewer;
  deepLinkTournamentId?: string | null;
}) {
  const t = useTranslations('ceTournaments');

  const [items, setItems] = useState<CETournamentCard[]>(tournaments);
  const itemsRef = useRef(items);
  itemsRef.current = items;
  const pendingRef = useRef<Set<string>>(new Set());
  const panelRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const [feedbackById, setFeedbackById] = useState<
    Record<string, PanelFeedback>
  >({});

  // Branch list: prefer the server-provided directory (shows empty branches);
  // otherwise derive it from the tournaments themselves.
  const branchList: CEBranchRef[] = useMemo(() => {
    if (branches && branches.length > 0) return branches;
    const map = new Map<string, string>();
    for (const it of items) {
      if (it.branch_id && it.branch_name && !map.has(it.branch_id)) {
        map.set(it.branch_id, it.branch_name);
      }
    }
    return [...map.entries()]
      .map(([id, name]) => ({ id, name }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [branches, items]);

  const grouped = useMemo(() => {
    return branchList.map((branch) => ({
      branch,
      tournaments: items
        .filter((it) => it.branch_id === branch.id)
        .sort((a, b) => {
          const byDate = a.tournament_date.localeCompare(b.tournament_date);
          if (byDate !== 0) return byDate;
          return (a.start_time ?? '').localeCompare(b.start_time ?? '');
        }),
    }));
  }, [branchList, items]);

  const deepLinkBranchId = useMemo(() => {
    if (!deepLinkTournamentId) return null;
    return items.find((it) => it.id === deepLinkTournamentId)?.branch_id ?? null;
  }, [deepLinkTournamentId, items]);

  const [expandedBranchId, setExpandedBranchId] = useState<string | null>(
    deepLinkBranchId,
  );

  // Deep link: expand the target's branch and scroll it into view on mount.
  useEffect(() => {
    if (!deepLinkBranchId) return;
    setExpandedBranchId(deepLinkBranchId);
  }, [deepLinkBranchId]);

  useEffect(() => {
    if (!deepLinkTournamentId || expandedBranchId !== deepLinkBranchId) return;
    const el = panelRefs.current.get(deepLinkTournamentId);
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [deepLinkTournamentId, deepLinkBranchId, expandedBranchId]);

  const setFeedback = useCallback((id: string, patch: PanelFeedback) => {
    setFeedbackById((prev) => ({ ...prev, [id]: { ...prev[id], ...patch } }));
  }, []);

  // Poll the schedule every 15s. Cards with an in-flight mutation are left
  // untouched so a refresh can't clobber an optimistic register/cancel.
  useEffect(() => {
    if (typeof fetch !== 'function') return;
    const id = setInterval(async () => {
      try {
        const res = await fetch('/api/chess-empire/tournaments');
        if (!res.ok) return;
        const data = (await res.json()) as { tournaments?: CETournamentCard[] };
        if (!Array.isArray(data.tournaments)) return;
        setItems((prev) => {
          const prevById = new Map(prev.map((it) => [it.id, it]));
          return data.tournaments!.map((fresh) =>
            pendingRef.current.has(fresh.id)
              ? prevById.get(fresh.id) ?? fresh
              : fresh,
          );
        });
      } catch {
        /* transient — next tick retries */
      }
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  const registerPanelRef = useCallback(
    (id: string, el: HTMLDivElement | null) => {
      if (el) panelRefs.current.set(id, el);
      else panelRefs.current.delete(id);
    },
    [],
  );

  const resolveError = useCallback(
    (
      data: { error?: string; message?: string },
      fallbackKey: 'errors.registerFailed' | 'errors.cancelFailed',
    ): string => {
      const code = data.error;
      if (code && t.has(`errors.${code}`)) return t(`errors.${code}`);
      return data.message || t(fallbackKey);
    },
    [t],
  );

  const viewerName =
    viewer.state === 'verified'
      ? viewer.studentName || t('yourself')
      : '';

  const handleRegister = useCallback(
    async (card: CETournamentCard) => {
      setFeedback(card.id, { error: null, notice: null });

      if (viewer.state === 'logged_out') {
        setFeedback(card.id, { notice: t('loggedOutNotice') });
        return;
      }
      if (viewer.state === 'unverified') {
        setFeedback(card.id, { notice: t('unverifiedNotice') });
        return;
      }

      const original = itemsRef.current.find((it) => it.id === card.id);
      if (!original) return;

      pendingRef.current.add(card.id);
      setFeedback(card.id, { busy: true });
      // Optimistic: flip to registered + drop the member's name into the roster.
      setItems((prev) =>
        prev.map((it) =>
          it.id === card.id
            ? {
                ...it,
                registration_id: it.registration_id ?? 'optimistic',
                is_registered: true,
                registered_count: it.registered_count + 1,
                roster: [...it.roster, viewerName],
              }
            : it,
        ),
      );

      try {
        const res = await fetch(
          `/api/chess-empire/tournaments/${card.id}/register`,
          { method: 'POST' },
        );
        const data = (await res.json().catch(() => ({}))) as {
          registration_id?: string;
          registered_count?: number;
          error?: string;
          message?: string;
        };
        if (!res.ok) {
          setItems((prev) =>
            prev.map((it) => (it.id === card.id ? original : it)),
          );
          setFeedback(card.id, {
            error: resolveError(data, 'errors.registerFailed'),
          });
          return;
        }
        setItems((prev) =>
          prev.map((it) =>
            it.id === card.id
              ? {
                  ...it,
                  registration_id:
                    data.registration_id ?? it.registration_id ?? 'registered',
                  registered_count: data.registered_count ?? it.registered_count,
                }
              : it,
          ),
        );
      } catch {
        setItems((prev) =>
          prev.map((it) => (it.id === card.id ? original : it)),
        );
        setFeedback(card.id, { error: t('errors.network') });
      } finally {
        pendingRef.current.delete(card.id);
        setFeedback(card.id, { busy: false });
      }
    },
    [viewer, viewerName, setFeedback, resolveError, t],
  );

  const handleCancel = useCallback(
    async (card: CETournamentCard) => {
      const original = itemsRef.current.find((it) => it.id === card.id);
      if (!original) return;

      pendingRef.current.add(card.id);
      setFeedback(card.id, { busy: true, error: null, notice: null });
      // Optimistic: drop one roster entry matching the member + un-register.
      setItems((prev) =>
        prev.map((it) => {
          if (it.id !== card.id) return it;
          const idx = it.roster.lastIndexOf(viewerName);
          const roster =
            idx >= 0
              ? [...it.roster.slice(0, idx), ...it.roster.slice(idx + 1)]
              : it.roster;
          return {
            ...it,
            registration_id: null,
            is_registered: false,
            registered_count: Math.max(0, it.registered_count - 1),
            roster,
          };
        }),
      );

      try {
        const res = await fetch(
          `/api/chess-empire/tournaments/${card.id}/register`,
          { method: 'DELETE' },
        );
        const data = (await res.json().catch(() => ({}))) as {
          error?: string;
          message?: string;
        };
        if (!res.ok) {
          setItems((prev) =>
            prev.map((it) => (it.id === card.id ? original : it)),
          );
          setFeedback(card.id, {
            error: resolveError(data, 'errors.cancelFailed'),
          });
        }
      } catch {
        setItems((prev) =>
          prev.map((it) => (it.id === card.id ? original : it)),
        );
        setFeedback(card.id, { error: t('errors.network') });
      } finally {
        pendingRef.current.delete(card.id);
        setFeedback(card.id, { busy: false });
      }
    },
    [viewerName, setFeedback, resolveError, t],
  );

  return (
    <div className="cet-root">
      <div className="cet-container">
        <div className="cet-header">
          <h1>{t('title')}</h1>
          <p className="cet-subtitle">{t('subtitle')}</p>
        </div>

        {viewer.state === 'logged_out' && (
          <div className="cet-banner">
            {t('loggedOutBanner')}{' '}
            <Link href={SIGN_IN_HREF} className="cet-banner-link">
              {t('signInToRegister')}
            </Link>
            .
          </div>
        )}
        {viewer.state === 'unverified' && (
          <div className="cet-banner">
            {t('unverifiedBanner')}{' '}
            <Link href={VERIFY_HREF} className="cet-banner-link">
              {t('verifyMembership')}
            </Link>
            .
          </div>
        )}

        {grouped.length === 0 ? (
          <div className="cet-empty">
            <p>{t('empty')}</p>
          </div>
        ) : (
          <div className="branches">
            {grouped.map(({ branch, tournaments: list }) => (
              <BranchCard
                key={branch.id}
                branch={branch}
                tournaments={list}
                expanded={expandedBranchId === branch.id}
                onToggle={() =>
                  setExpandedBranchId((cur) =>
                    cur === branch.id ? null : branch.id,
                  )
                }
                viewer={viewer}
                feedbackById={feedbackById}
                highlightId={deepLinkTournamentId}
                registerPanelRef={registerPanelRef}
                onRegister={handleRegister}
                onCancel={handleCancel}
              />
            ))}
          </div>
        )}
      </div>

      <style jsx global>{`
        .cet-root {
          background: linear-gradient(135deg, #f5f7fa 0%, #e4e9f0 100%);
          min-height: 100%;
          color: #1e293b;
        }
        .cet-container {
          max-width: 900px;
          margin: 0 auto;
          padding: 24px 16px 80px;
        }
        .cet-header {
          text-align: center;
          margin-bottom: 24px;
        }
        .cet-header h1 {
          font-size: 2rem;
          font-weight: 800;
          color: #1e293b;
          margin-bottom: 8px;
        }
        .cet-subtitle {
          color: #64748b;
          font-size: 0.95rem;
        }
        .cet-banner {
          background: #fff;
          border: 1px solid #e2e8f0;
          border-radius: 12px;
          padding: 14px 16px;
          margin-bottom: 16px;
          color: #475569;
          font-size: 0.9rem;
        }
        .cet-banner-link,
        .notice-link {
          color: #2563eb;
          font-weight: 600;
          text-decoration: underline;
        }
        .cet-empty {
          border: 1px dashed #cbd5e1;
          border-radius: 14px;
          padding: 40px 20px;
          text-align: center;
          color: #94a3b8;
        }

        .cet-root .branches {
          display: flex;
          flex-direction: column;
          gap: 12px;
        }
        .cet-root .branch-card {
          background: #fff;
          border-radius: 14px;
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
          overflow: hidden;
          transition: box-shadow 0.2s;
        }
        .cet-root .branch-card:hover {
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
        }
        .cet-root .branch-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 14px;
          flex-wrap: wrap;
          padding: 18px 20px;
          cursor: pointer;
          user-select: none;
        }
        .cet-root .branch-name {
          font-size: 1.15rem;
          font-weight: 700;
          color: #1e293b;
          flex: 1 1 auto;
          min-width: 0;
          overflow-wrap: anywhere;
        }
        .cet-root .branch-header-right {
          display: flex;
          align-items: center;
          gap: 10px;
          flex: 0 0 auto;
        }
        .cet-root .branch-chevron {
          transition: transform 0.25s ease;
          color: #94a3b8;
        }
        .cet-root .branch-card.expanded .branch-chevron {
          transform: rotate(180deg);
        }
        .cet-root .count-badge {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
          color: #fff;
          font-size: 0.78rem;
          font-weight: 600;
          padding: 5px 12px;
          border-radius: 999px;
          box-shadow: 0 1px 3px rgba(59, 130, 246, 0.25);
          white-space: nowrap;
        }
        .cet-root .count-badge.zero {
          background: #e2e8f0;
          color: #64748b;
          box-shadow: none;
        }
        .cet-root .tournaments-list {
          padding: 0 20px 18px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        .cet-root .empty-row {
          padding: 14px 0;
          text-align: center;
          color: #94a3b8;
          font-size: 0.9rem;
        }
        .cet-root .tournament-row {
          background: #f8fafc;
          border: 1px solid #e2e8f0;
          border-radius: 10px;
          overflow: hidden;
          transition: border-color 0.2s;
        }
        .cet-root .tournament-row.expanded {
          border-color: #3b82f6;
        }
        .cet-root .tournament-row.highlighted {
          border-color: #2563eb;
          box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.25);
        }
        .cet-root .tournament-summary {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 12px 16px;
        }
        .cet-root .tournament-title {
          font-weight: 600;
          color: #1e293b;
          font-size: 0.97rem;
        }
        .cet-root .razryad-badge {
          display: inline-block;
          margin-top: 4px;
          background: #f3e8ff;
          color: #7c3aed;
          font-size: 0.68rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.04em;
          padding: 2px 8px;
          border-radius: 999px;
        }
        .cet-root .tournament-meta {
          display: flex;
          align-items: center;
          gap: 12px;
          color: #64748b;
          font-size: 0.85rem;
          flex-wrap: wrap;
        }
        .cet-root .tournament-meta .pill {
          background: #eff6ff;
          color: #2563eb;
          padding: 3px 10px;
          border-radius: 999px;
          font-weight: 600;
          font-size: 0.75rem;
        }
        .cet-root .tournament-meta .pill.full {
          background: #fef3c7;
          color: #b45309;
        }
        .cet-root .detail-inner {
          padding: 16px;
          border-top: 1px solid #e2e8f0;
          background: #fff;
        }
        .cet-root .detail-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 12px 18px;
          margin-bottom: 14px;
        }
        .cet-root .detail-item .label {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: #94a3b8;
          font-weight: 600;
          margin-bottom: 2px;
        }
        .cet-root .detail-item .value {
          font-size: 0.95rem;
          color: #1e293b;
          font-weight: 600;
        }
        .cet-root .info-box {
          background: #f1f5f9;
          border-radius: 8px;
          padding: 10px 12px;
          color: #475569;
          font-size: 0.88rem;
          margin-bottom: 14px;
          line-height: 1.4;
        }
        .cet-root .capacity-bar {
          background: #e2e8f0;
          height: 10px;
          border-radius: 999px;
          overflow: hidden;
          margin-top: 6px;
        }
        .cet-root .capacity-fill {
          height: 100%;
          background: linear-gradient(90deg, #10b981 0%, #059669 100%);
          transition: width 0.3s ease;
        }
        .cet-root .capacity-fill.warn {
          background: linear-gradient(90deg, #f59e0b 0%, #d97706 100%);
        }
        .cet-root .capacity-fill.full {
          background: linear-gradient(90deg, #ef4444 0%, #dc2626 100%);
        }
        .cet-root .roster {
          background: #f8fafc;
          border-radius: 10px;
          padding: 12px;
          margin-bottom: 14px;
          max-height: 240px;
          overflow-y: auto;
        }
        .cet-root .roster-empty {
          color: #94a3b8;
          font-size: 0.85rem;
          text-align: center;
          padding: 8px 0;
        }
        .cet-root .roster-list {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .cet-root .roster-item {
          display: flex;
          align-items: center;
          gap: 10px;
          font-size: 0.88rem;
          color: #334155;
        }
        .cet-root .roster-num {
          width: 24px;
          text-align: right;
          color: #94a3b8;
          font-weight: 600;
          font-size: 0.78rem;
        }
        .cet-root .register-btn {
          width: 100%;
          padding: 12px;
          border: none;
          background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
          color: #fff;
          font-weight: 700;
          font-size: 0.95rem;
          border-radius: 10px;
          cursor: pointer;
          transition: all 0.15s;
          box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
        }
        .cet-root .register-btn:hover:not(:disabled) {
          transform: translateY(-1px);
          box-shadow: 0 4px 10px rgba(59, 130, 246, 0.4);
        }
        .cet-root .register-btn:disabled {
          background: #e2e8f0;
          color: #94a3b8;
          cursor: not-allowed;
          box-shadow: none;
        }
        .cet-root .registered-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }
        .cet-root .registered-label {
          color: #059669;
          font-weight: 600;
          font-size: 0.9rem;
        }
        .cet-root .cancel-btn {
          padding: 8px 14px;
          border: 1px solid #cbd5e1;
          background: #fff;
          color: #475569;
          font-size: 0.85rem;
          font-weight: 500;
          border-radius: 8px;
          cursor: pointer;
        }
        .cet-root .cancel-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .cet-root .register-note {
          margin-top: 10px;
          text-align: center;
          font-size: 0.8rem;
          line-height: 1.4;
          color: #64748b;
        }
        .cet-root .register-notice {
          text-align: left;
        }
        .cet-root .register-error {
          margin-top: 10px;
          color: #dc2626;
          font-size: 0.85rem;
        }
        .cet-root .countdown-block {
          margin-bottom: 14px;
          text-align: center;
        }
        .cet-root .countdown-label {
          font-size: 0.7rem;
          text-transform: uppercase;
          letter-spacing: 0.06em;
          color: #64748b;
          font-weight: 700;
          margin-bottom: 8px;
        }
        .cet-root .countdown-cards {
          display: flex;
          justify-content: center;
          gap: 8px;
        }
        .cet-root .countdown-card {
          position: relative;
          flex: 1 1 0;
          max-width: 88px;
          background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
          border-radius: 10px;
          padding: 12px 4px 8px;
          box-shadow: 0 2px 6px rgba(15, 23, 42, 0.18);
          overflow: hidden;
        }
        .cet-root .countdown-number {
          font-size: 1.9rem;
          font-weight: 800;
          line-height: 1;
          color: #fff;
          font-variant-numeric: tabular-nums;
        }
        .cet-root .countdown-unit {
          display: block;
          margin-top: 6px;
          font-size: 0.62rem;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: #94a3b8;
          font-weight: 600;
        }
        .cet-root .countdown-block.urgent .countdown-number {
          color: #f59e0b;
        }
        .cet-root .countdown-block.critical .countdown-number {
          color: #ef4444;
          animation: cetPulse 1s ease-in-out infinite;
        }
        @keyframes cetPulse {
          0%,
          100% {
            opacity: 1;
          }
          50% {
            opacity: 0.7;
          }
        }
        @media (max-width: 640px) {
          .cet-container {
            padding: 16px 12px 80px;
          }
          .cet-header h1 {
            font-size: 1.5rem;
          }
          .cet-root .detail-grid {
            grid-template-columns: 1fr;
            gap: 10px;
          }
          .cet-root .countdown-number {
            font-size: 1.5rem;
          }
        }
      `}</style>
    </div>
  );
}
