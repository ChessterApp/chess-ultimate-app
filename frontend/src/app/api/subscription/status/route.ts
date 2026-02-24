import { NextResponse } from 'next/server';
import { auth } from '@clerk/nextjs/server';

// TEMPORARY: All registered users get full premium access
// Original Supabase subscription check removed to avoid module-level init crash in standalone mode
export async function GET() {
  try {
    const { userId } = await auth();

    if (!userId) {
      return NextResponse.json({ active: false, plan: null, reason: 'not_authenticated' });
    }

    return NextResponse.json({
      active: true,
      plan: 'premium',
      status: 'active',
    });
  } catch (err: any) {
    console.error('[Subscription Status] Error:', err.message);
    return NextResponse.json({ active: false, plan: null, error: err.message });
  }
}
