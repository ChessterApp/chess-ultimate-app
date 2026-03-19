'use client'

/**
 * SocialButtons - Client island for social media buttons in footer
 * Handles hover states for social media links
 */
export function SocialButtons() {
  return (
    <div className="flex gap-4">
      <button
        className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors"
        aria-label="Twitter/X"
      >
        <span>𝕏</span>
      </button>
      <button
        className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors"
        aria-label="Instagram"
      >
        <span>📸</span>
      </button>
      <button
        className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors"
        aria-label="YouTube"
      >
        <span>▶️</span>
      </button>
    </div>
  )
}
