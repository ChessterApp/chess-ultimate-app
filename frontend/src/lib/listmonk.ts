/**
 * Listmonk API helper functions
 */

const LISTMONK_API_URL = process.env.LISTMONK_API_URL || 'http://localhost:9000';
const LISTMONK_API_USER = process.env.LISTMONK_API_USER || 'admin';
const LISTMONK_API_PASS = process.env.LISTMONK_API_PASS || '';

// List IDs
export const LISTS = {
  ALL_USERS: 3,
  WELCOME_SEQUENCE: 4,
  ACTIVE_LEARNERS: 5,
  CHURNED_USERS: 6,
  PREMIUM: 7,
} as const;

function authHeader(): string {
  return 'Basic ' + Buffer.from(`${LISTMONK_API_USER}:${LISTMONK_API_PASS}`).toString('base64');
}

async function listmonkFetch(path: string, options: RequestInit = {}) {
  const res = await fetch(`${LISTMONK_API_URL}/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: authHeader(),
      ...options.headers,
    },
  });
  return res;
}

export async function createSubscriber(
  email: string,
  name: string,
  listIds: number[] = [LISTS.ALL_USERS, LISTS.WELCOME_SEQUENCE],
  attribs: Record<string, unknown> = {}
): Promise<{ id: number; created: boolean }> {
  const res = await listmonkFetch('/subscribers', {
    method: 'POST',
    body: JSON.stringify({
      email,
      name,
      status: 'enabled',
      lists: listIds,
      attribs,
      preconfirm_subscriptions: true,
    }),
  });

  if (res.status === 409) {
    // Already exists — find and update list subscriptions
    console.log(`[listmonk] Subscriber ${email} already exists, updating lists`);
    const existing = await findSubscriberByEmail(email);
    if (existing) {
      await addSubscriberToLists(existing.id, listIds);
      return { id: existing.id, created: false };
    }
    return { id: 0, created: false };
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Listmonk createSubscriber failed (${res.status}): ${text}`);
  }

  const data = await res.json();
  return { id: data.data.id, created: true };
}

export async function findSubscriberByEmail(email: string): Promise<{ id: number; email: string } | null> {
  const res = await listmonkFetch(`/subscribers?query=subscribers.email='${encodeURIComponent(email)}'&page=1&per_page=1`);
  if (!res.ok) return null;
  const data = await res.json();
  if (data.data?.results?.length > 0) {
    return data.data.results[0];
  }
  return null;
}

export async function addSubscriberToLists(subscriberId: number, listIds: number[]) {
  const res = await listmonkFetch('/subscribers/lists', {
    method: 'PUT',
    body: JSON.stringify({
      ids: [subscriberId],
      action: 'add',
      target_list_ids: listIds,
      status: 'confirmed',
    }),
  });
  return res.ok;
}

export async function blocklistSubscriber(email: string): Promise<boolean> {
  const subscriber = await findSubscriberByEmail(email);
  if (!subscriber) {
    console.log(`[listmonk] Subscriber ${email} not found for blocklisting`);
    return false;
  }

  const res = await listmonkFetch(`/subscribers/${subscriber.id}/blocklist`, {
    method: 'PUT',
  });

  if (!res.ok) {
    const text = await res.text();
    console.error(`[listmonk] Blocklist failed for ${email}: ${text}`);
    return false;
  }

  console.log(`[listmonk] Blocklisted subscriber ${email} (id: ${subscriber.id})`);
  return true;
}
