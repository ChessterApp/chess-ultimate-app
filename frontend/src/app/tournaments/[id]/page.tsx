import { headers } from 'next/headers';
import Link from 'next/link';

interface Tournament {
  id: string;
  name: string;
  description: string | null;
  location: string;
  city: string | null;
  country: string | null;
  start_date: string;
  end_date: string;
  registration_deadline: string;
  time_control: string;
  format: string | null;
  max_participants: number | null;
  entry_fee: number;
  currency: string;
  prize_fund: number | null;
  rating_category: string | null;
  min_rating: number | null;
  max_rating: number | null;
  is_rated: boolean;
  tournament_mode: 'offline' | 'online';
  status: string;
}

interface Participant {
  player_name: string;
  rating_at_registration: number | null;
  registration_status: string;
}

async function fetchTournament(id: string): Promise<Tournament | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/tournaments/${id}`, {
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchParticipants(id: string): Promise<Participant[]> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/tournaments/${id}/participants`, {
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) return [];
    const data = await res.json();
    return data.participants || [];
  } catch {
    return [];
  }
}

function InfoRow({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="flex justify-between py-2 border-b border-gray-100 dark:border-gray-700 last:border-0">
      <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{value}</span>
    </div>
  );
}

export default async function TournamentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [tournament, participants] = await Promise.all([
    fetchTournament(id),
    fetchParticipants(id),
  ]);

  if (!tournament) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Tournament Not Found</h1>
        <p className="text-gray-500 dark:text-gray-400 mt-2">This tournament does not exist or has been removed.</p>
      </div>
    );
  }

  const deadlinePassed = tournament.registration_deadline
    ? new Date(tournament.registration_deadline) < new Date()
    : false;

  const canRegister = !deadlinePassed &&
    ['upcoming', 'registration_open'].includes(tournament.status) &&
    (!tournament.max_participants || participants.length < tournament.max_participants);

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <Link href="/tournaments" className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block">
        &larr; All Tournaments
      </Link>

      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">{tournament.name}</h1>
      {tournament.description && (
        <p className="text-gray-600 dark:text-gray-400 mb-6">{tournament.description}</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Details */}
        <div className="md:col-span-2 space-y-6">
          <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3">Details</h2>
            <InfoRow label="Status" value={tournament.status.replace('_', ' ')} />
            <InfoRow label="Location" value={tournament.location} />
            <InfoRow label="City" value={tournament.city} />
            <InfoRow label="Country" value={tournament.country} />
            <InfoRow label="Start Date" value={new Date(tournament.start_date).toLocaleDateString()} />
            <InfoRow label="End Date" value={new Date(tournament.end_date).toLocaleDateString()} />
            <InfoRow label="Registration Deadline" value={new Date(tournament.registration_deadline).toLocaleDateString()} />
            <InfoRow label="Time Control" value={tournament.time_control} />
            <InfoRow label="Format" value={tournament.format} />
            <InfoRow
              label="Mode"
              value={tournament.tournament_mode === 'online' ? 'Online' : 'Offline (OTB)'}
            />
            <InfoRow label="Rated" value={tournament.is_rated ? 'Yes (Local App Rating)' : 'No'} />
            {tournament.entry_fee > 0 && (
              <InfoRow label="Entry Fee" value={`${tournament.entry_fee} ${tournament.currency}`} />
            )}
            {tournament.prize_fund && (
              <InfoRow label="Prize Fund" value={`${tournament.prize_fund} ${tournament.currency}`} />
            )}
            {tournament.rating_category && (
              <InfoRow label="Rating Category" value={tournament.rating_category} />
            )}
            {tournament.min_rating && (
              <InfoRow label="Min Rating" value={tournament.min_rating} />
            )}
            {tournament.max_rating && (
              <InfoRow label="Max Rating" value={tournament.max_rating} />
            )}
          </section>

          {/* Participants Preview */}
          <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                Participants ({participants.length}{tournament.max_participants ? `/${tournament.max_participants}` : ''})
              </h2>
            </div>
            {participants.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">No participants registered yet.</p>
            ) : (
              <div className="space-y-1">
                {participants.slice(0, 10).map((p, i) => (
                  <div key={i} className="flex justify-between text-sm py-1">
                    <span className="text-gray-900 dark:text-gray-100">{p.player_name}</span>
                    {p.rating_at_registration && (
                      <span className="text-gray-500 dark:text-gray-400">{p.rating_at_registration}</span>
                    )}
                  </div>
                ))}
                {participants.length > 10 && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 pt-1">
                    +{participants.length - 10} more
                  </p>
                )}
              </div>
            )}
          </section>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {canRegister && (
            <Link
              href={`/tournaments/${tournament.id}/register`}
              className="block w-full text-center px-4 py-3 text-sm font-medium text-white rounded-lg transition-colors"
              style={{ backgroundColor: 'var(--brand-primary)' }}
            >
              Register
            </Link>
          )}

          {tournament.status === 'completed' && (
            <Link
              href={`/tournaments/${tournament.id}/results`}
              className="block w-full text-center px-4 py-3 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              View Results
            </Link>
          )}

          {/* Quick Info Card */}
          <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
            <div className="space-y-3">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Time Control</p>
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{tournament.time_control}</p>
              </div>
              {tournament.format && (
                <div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">Format</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{tournament.format}</p>
                </div>
              )}
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Entry Fee</p>
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                  {tournament.entry_fee > 0 ? `${tournament.entry_fee} ${tournament.currency}` : 'Free'}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
