'use client'

/**
 * HeroAnimatedBackground - Client island for hero section animated background elements
 * Handles animated gradient blobs and floating chess pieces with CSS animations
 */
export function HeroAnimatedBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none hidden lg:block">
      <div className="absolute -top-24 -left-24 w-96 h-96 bg-purple-500/20 rounded-full blur-3xl animate-pulse" />
      <div
        className="absolute -bottom-32 -right-32 w-[30rem] h-[30rem] bg-indigo-400/15 rounded-full blur-3xl"
        style={{ animation: 'pulse 4s ease-in-out infinite' }}
      />
      <div
        className="absolute top-1/3 right-1/4 w-64 h-64 bg-violet-300/10 rounded-full blur-2xl"
        style={{ animation: 'pulse 6s ease-in-out infinite 1s' }}
      />
      {/* Floating chess pieces */}
      <div
        className="absolute top-20 right-[15%] text-white/5 text-8xl"
        style={{ animation: 'bounce-slow 5s ease-in-out infinite' }}
      >
        ♞
      </div>
      <div
        className="absolute bottom-20 left-[10%] text-white/5 text-7xl"
        style={{ animation: 'bounce-slow 7s ease-in-out infinite 2s' }}
      >
        ♛
      </div>
    </div>
  )
}
