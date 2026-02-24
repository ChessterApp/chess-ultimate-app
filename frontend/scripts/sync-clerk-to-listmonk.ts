#!/usr/bin/env npx tsx
/**
 * One-time script: Sync all existing Clerk users to Listmonk.
 * Usage: cd frontend && npx tsx scripts/sync-clerk-to-listmonk.ts
 */

import 'dotenv/config';

const CLERK_SECRET = process.env.CLERK_SECRET_KEY!;
const LISTMONK_URL = process.env.LISTMONK_API_URL || 'http://localhost:9000';
const LISTMONK_USER = process.env.LISTMONK_API_USER || 'admin';
const LISTMONK_PASS = process.env.LISTMONK_API_PASS!;

if (!CLERK_SECRET || !LISTMONK_PASS) {
  console.error('Missing required env vars: CLERK_SECRET_KEY, LISTMONK_API_PASS');
  process.exit(1);
}
const ALL_USERS_LIST = 3;

const listmonkAuth = 'Basic ' + Buffer.from(`${LISTMONK_USER}:${LISTMONK_PASS}`).toString('base64');

async function fetchAllClerkUsers() {
  const users: any[] = [];
  let offset = 0;
  const limit = 100;

  while (true) {
    const res = await fetch(`https://api.clerk.com/v1/users?limit=${limit}&offset=${offset}`, {
      headers: { Authorization: `Bearer ${CLERK_SECRET}` },
    });
    if (!res.ok) throw new Error(`Clerk API error: ${res.status}`);
    const batch = await res.json();
    if (batch.length === 0) break;
    users.push(...batch);
    if (batch.length < limit) break;
    offset += limit;
  }

  return users;
}

async function addToListmonk(email: string, name: string, clerkId: string) {
  const res = await fetch(`${LISTMONK_URL}/api/subscribers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: listmonkAuth },
    body: JSON.stringify({
      email,
      name,
      status: 'enabled',
      lists: [ALL_USERS_LIST],
      attribs: { clerk_id: clerkId, source: 'bulk_sync' },
      preconfirm_subscriptions: true,
    }),
  });

  if (res.status === 409) return 'exists';
  if (!res.ok) {
    const t = await res.text();
    console.error(`  Failed for ${email}: ${t}`);
    return 'error';
  }
  return 'created';
}

async function main() {
  console.log('Fetching Clerk users...');
  const users = await fetchAllClerkUsers();
  console.log(`Found ${users.length} users`);

  let created = 0, exists = 0, errors = 0, skipped = 0;

  for (const user of users) {
    const email = user.email_addresses?.[0]?.email_address;
    if (!email) { skipped++; continue; }

    const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || email.split('@')[0];
    const result = await addToListmonk(email, name, user.id);

    if (result === 'created') created++;
    else if (result === 'exists') exists++;
    else errors++;
  }

  console.log(`\nDone! Created: ${created}, Already existed: ${exists}, Errors: ${errors}, Skipped (no email): ${skipped}`);
}

main().catch(console.error);
