export default function CoachLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    // Phones: the page sizes itself between the app bars (see coach/page.tsx);
    // a full-screen minimum here would push it past them again.
    <div className="md:min-h-screen" style={{ background: '#1a1a2e' }}>
      {children}
    </div>
  );
}
