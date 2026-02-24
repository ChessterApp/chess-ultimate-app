import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-purple-50 via-white to-indigo-50">
      <div className="text-center px-4 max-w-lg">
        {/* Chesster mascot logo */}
        <div className="mb-8 flex justify-center">
          <div className="relative">
            <img
              src="/static/images/chesster-logo-v3.png"
              alt="Chesster"
              className="w-32 h-32 md:w-40 md:h-40 drop-shadow-lg"
            />
            <div className="absolute -bottom-2 -right-2 bg-purple-600 text-white text-sm font-bold px-3 py-1 rounded-full shadow-lg">
              404
            </div>
          </div>
        </div>

        {/* Message */}
        <h1 className="text-4xl md:text-5xl font-bold text-gray-800 mb-4">
          Page not found
        </h1>
        <p className="text-gray-500 text-lg mb-10">
          Looks like this move isn&apos;t on the board. Let&apos;s get you back to the game!
        </p>

        {/* Navigation links */}
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/dashboard"
            className="inline-flex items-center justify-center px-8 py-3 bg-purple-600 hover:bg-purple-700 text-white font-semibold rounded-2xl shadow-lg hover:shadow-xl transition-all duration-200 transform hover:scale-105 active:scale-95"
          >
            Go to Dashboard
          </Link>
          <Link
            href="/puzzle"
            className="inline-flex items-center justify-center px-8 py-3 bg-white border-2 border-purple-200 hover:border-purple-400 text-purple-600 font-semibold rounded-2xl shadow-sm hover:shadow-md transition-all duration-200 transform hover:scale-105 active:scale-95"
          >
            🧩 Try Puzzles
          </Link>
          <Link
            href="/"
            className="inline-flex items-center justify-center px-8 py-3 text-gray-600 hover:text-purple-600 font-medium rounded-2xl transition-colors duration-200"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
}
