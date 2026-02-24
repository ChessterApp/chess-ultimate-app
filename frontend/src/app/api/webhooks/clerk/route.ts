import { Webhook } from 'svix';
import { headers } from 'next/headers';
import { NextResponse } from 'next/server';
import { createSubscriber, blocklistSubscriber, LISTS } from '@/lib/listmonk';

type ClerkWebhookEvent = {
  type: string;
  data: Record<string, unknown>;
};

export async function POST(req: Request) {
  const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SECRET;
  if (!WEBHOOK_SECRET) {
    console.error('[clerk-webhook] CLERK_WEBHOOK_SECRET not set');
    return NextResponse.json({ error: 'Server misconfigured' }, { status: 500 });
  }

  // Verify signature
  const headerPayload = await headers();
  const svix_id = headerPayload.get('svix-id');
  const svix_timestamp = headerPayload.get('svix-timestamp');
  const svix_signature = headerPayload.get('svix-signature');

  if (!svix_id || !svix_timestamp || !svix_signature) {
    return NextResponse.json({ error: 'Missing svix headers' }, { status: 400 });
  }

  const body = await req.text();
  const wh = new Webhook(WEBHOOK_SECRET);

  let evt: ClerkWebhookEvent;
  try {
    evt = wh.verify(body, {
      'svix-id': svix_id,
      'svix-timestamp': svix_timestamp,
      'svix-signature': svix_signature,
    }) as ClerkWebhookEvent;
  } catch (err) {
    console.error('[clerk-webhook] Verification failed:', err);
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 });
  }

  console.log(`[clerk-webhook] Received event: ${evt.type}`);

  try {
    switch (evt.type) {
      case 'user.created': {
        const { email_addresses, first_name, last_name, id } = evt.data as {
          email_addresses: { email_address: string; id: string }[];
          first_name: string | null;
          last_name: string | null;
          id: string;
        };

        const primaryEmail = email_addresses?.[0]?.email_address;
        if (!primaryEmail) {
          console.warn('[clerk-webhook] user.created with no email, skipping');
          break;
        }

        const name = [first_name, last_name].filter(Boolean).join(' ') || primaryEmail.split('@')[0];

        const result = await createSubscriber(
          primaryEmail,
          name,
          [LISTS.ALL_USERS, LISTS.WELCOME_SEQUENCE],
          { clerk_id: id, source: 'clerk_webhook' }
        );

        console.log(`[clerk-webhook] Subscriber ${primaryEmail}: id=${result.id}, new=${result.created}`);
        break;
      }

      case 'user.deleted': {
        const { email_addresses } = evt.data as {
          email_addresses?: { email_address: string }[];
        };

        const email = email_addresses?.[0]?.email_address;
        if (email) {
          await blocklistSubscriber(email);
        } else {
          console.warn('[clerk-webhook] user.deleted with no email');
        }
        break;
      }

      default:
        console.log(`[clerk-webhook] Unhandled event type: ${evt.type}`);
    }
  } catch (err) {
    console.error(`[clerk-webhook] Error processing ${evt.type}:`, err);
    // Return 200 to prevent retries for processing errors
    return NextResponse.json({ error: 'Processing failed', received: true }, { status: 200 });
  }

  return NextResponse.json({ received: true });
}
