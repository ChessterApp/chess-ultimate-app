"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";

export default function OnboardingGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isSignedIn, isLoaded } = useAuth();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;

    if (isSignedIn) {
      const completed = localStorage.getItem("chesster_onboarding_complete");
      if (!completed) {
        router.replace("/onboarding");
        return;
      }
    }
    setChecked(true);
  }, [isSignedIn, isLoaded, router]);

  if (!checked) return null;
  return <>{children}</>;
}
