import { NextRequest, NextResponse } from "next/server";
import { auth } from '@clerk/nextjs/server';

const VALID_PLANS = new Set([
  process.env.NEXT_PUBLIC_WHOP_WEEKLY_PLAN,
  process.env.NEXT_PUBLIC_WHOP_MONTHLY_PLAN,
  process.env.NEXT_PUBLIC_WHOP_YEARLY_PLAN,
]);

export async function POST(req: NextRequest) {
  try {
    const { planId } = await req.json();

    if (!planId || !VALID_PLANS.has(planId)) {
      return NextResponse.json({ error: "Invalid plan" }, { status: 400 });
    }

    const redirectUrl = encodeURIComponent("https://chesster.io/onboarding?step=complete");
    
    // Try to get Clerk user ID to pass as metadata
    let checkoutUrl = `https://whop.com/checkout/${planId}?d=${redirectUrl}`;
    
    try {
      const { userId } = await auth();
      if (userId) {
        checkoutUrl += `&metadata[clerk_user_id]=${encodeURIComponent(userId)}`;
      }
    } catch {
      // Not authenticated — still allow checkout
    }

    return NextResponse.json({ checkoutUrl });
  } catch {
    return NextResponse.json({ error: "Internal error" }, { status: 500 });
  }
}
