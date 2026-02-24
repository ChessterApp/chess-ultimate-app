import { GameDataProvider } from '@/lib/onboarding/GameDataContext';

export default function OnboardingLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <GameDataProvider>
      <div className="min-h-screen bg-gradient-to-b from-purple-600 to-purple-800 safe-area-inset">
        {children}
      </div>
    </GameDataProvider>
  );
}
