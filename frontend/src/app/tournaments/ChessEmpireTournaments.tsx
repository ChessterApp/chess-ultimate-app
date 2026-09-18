/**
 * Chess Empire tournaments — server view.
 *
 * Loads the shared schedule snapshot (branches + rosters + the viewer's own
 * registration status) and hands a plain-data payload to the client view that
 * renders the branch accordion and drives one-click register/cancel. All CE
 * calls (and the service key) stay server-side.
 */
import 'server-only';
import { loadCETournamentSnapshot } from '@/lib/ce-tournaments-data';
import CETournamentsView, { type CEViewer } from './CETournamentsView';

export default async function ChessEmpireTournaments({
  deepLinkTournamentId = null,
}: {
  deepLinkTournamentId?: string | null;
}) {
  const { membership, studentName, members, branches, tournaments } =
    await loadCETournamentSnapshot();

  const viewer: CEViewer =
    membership === 'verified'
      ? { state: 'verified', studentName, members }
      : membership === 'unverified'
        ? { state: 'unverified' }
        : { state: 'logged_out' };

  return (
    <CETournamentsView
      tournaments={tournaments}
      branches={branches}
      viewer={viewer}
      deepLinkTournamentId={deepLinkTournamentId}
    />
  );
}
