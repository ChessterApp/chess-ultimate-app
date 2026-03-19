export default function PageSkeleton() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-white dark:bg-[#141414]">
      <div className="flex flex-col items-center gap-4">
        <div className="flex gap-3">
          {['♚', '♛', '♜', '♝', '♞', '♟'].map((piece, i) => (
            <div
              key={i}
              className="text-4xl animate-bounce"
              style={{
                animationDelay: `${i * 0.1}s`,
                animationDuration: '1s',
              }}
            >
              {piece}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
