// F11 — delete the PostHog person (and their events) when Clerk deletes the
// user. Called from the Clerk `user.deleted` webhook. Best-effort: missing env
// is a logged skip and API errors are logged, never thrown — the rest of the
// deletion cascade must still run.
//
// API: GET  /api/projects/:project_id/persons/?distinct_id=<id>  → { results: [{ uuid }] }
//      DELETE /api/projects/:project_id/persons/:uuid/?delete_events=true
// Auth: personal API key (scope person:write) as a Bearer token.

import 'server-only';

const DEFAULT_API_HOST = 'https://us.posthog.com';

type PersonLookup = { results?: Array<{ uuid?: string; id?: string | number }> };

export async function deletePostHogPerson(distinctId: string): Promise<void> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  if (!apiKey || !projectId) {
    console.warn(
      '[posthog-delete] POSTHOG_PERSONAL_API_KEY / POSTHOG_PROJECT_ID not set, skipping person delete',
    );
    return;
  }
  const host = (process.env.POSTHOG_API_HOST || DEFAULT_API_HOST).replace(/\/+$/, '');
  const base = `${host}/api/projects/${encodeURIComponent(projectId)}/persons`;
  const headers = { Authorization: `Bearer ${apiKey}` };

  try {
    const lookup = await fetch(`${base}/?distinct_id=${encodeURIComponent(distinctId)}`, {
      headers,
    });
    if (!lookup.ok) throw new Error(`person lookup HTTP ${lookup.status}`);
    const body = (await lookup.json()) as PersonLookup;
    const person = body.results?.[0];
    const personId = person?.uuid ?? person?.id;
    if (personId === undefined) {
      console.info(`[posthog-delete] no PostHog person for user=${distinctId}`);
      return;
    }
    const del = await fetch(
      `${base}/${encodeURIComponent(String(personId))}/?delete_events=true`,
      { method: 'DELETE', headers },
    );
    if (!del.ok) throw new Error(`person delete HTTP ${del.status}`);
    console.info(`[posthog-delete] deleted PostHog person for user=${distinctId}`);
  } catch (err) {
    console.error('[posthog-delete] failed:', err);
  }
}
