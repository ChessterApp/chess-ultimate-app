export default function CoachLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen" style={{ background: '#1a1a2e' }}>
      {children}
    </div>
  );
}
