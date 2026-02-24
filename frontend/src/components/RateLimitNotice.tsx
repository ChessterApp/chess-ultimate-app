'use client';

export default function RateLimitNotice({ onRetry }: { onRetry?: () => void }) {
  return (
    <div className="bg-purple-50 border border-purple-200 rounded-xl p-4 text-center">
      <div className="text-3xl mb-2">♞</div>
      <h3 className="font-semibold text-purple-800 mb-1">Take a breath, champion</h3>
      <p className="text-purple-600 text-sm mb-3">
        You&apos;re moving faster than a blitz game! Please wait a moment before trying again.
      </p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700 transition-colors"
        >
          Try Again
        </button>
      )}
    </div>
  );
}
