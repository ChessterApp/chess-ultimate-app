import type { ReviewJob, ReviewSource } from './types';

/** Thrown by {@link fetchReview} on a non-2xx poll, carrying the HTTP status so
 *  the caller can distinguish a terminal 404 (unknown id) from a retryable
 *  network/5xx blip. */
export class ReviewFetchError extends Error {
  status: number;
  constructor(status: number) {
    super(`Review fetch failed (${status})`);
    this.name = 'ReviewFetchError';
    this.status = status;
  }
}

/** POST a PGN to the review pipeline. Returns the review id + initial status.
 *  `source` only tags the server-side `game_review_completed` analytics event. */
export async function startReview(
  pgn: string,
  source?: ReviewSource,
): Promise<{ review_id: string; status: string }> {
  const res = await fetch('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pgn, source }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data?.error || `Review request failed (${res.status})`);
  }
  return res.json();
}

/** Poll the review job. */
export async function fetchReview(id: string): Promise<ReviewJob> {
  const res = await fetch(`/api/review/${id}`, { cache: 'no-store' });
  if (!res.ok) {
    throw new ReviewFetchError(res.status);
  }
  return res.json();
}
