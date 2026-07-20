/**
 * Explicit error/retry screen for the Chess Empire tenant dashboard.
 *
 * Rendered when `renderEmpireHomepage` returns `lookup_error` — a required
 * fetch (membership / profile) threw. On the tenant host we must NOT silently
 * fall back to the generic Chesster dashboard (which would mask the failure as
 * "personalization missing"), so we show an honest retry surface instead.
 */
export default function EmpireError() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4 text-center">
      <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-xl">
        <h1 className="text-2xl font-bold text-gray-800">
          We hit a snag loading your dashboard
        </h1>
        <p className="mt-3 text-sm text-gray-500">
          Something went wrong on our end. Please try again in a moment.
        </p>
        <a
          href="/dashboard"
          className="mt-6 inline-flex w-full items-center justify-center rounded-2xl border-b-4 border-purple-800 bg-purple-600 py-4 font-bold uppercase tracking-wide text-white transition-all hover:bg-purple-700 active:translate-y-0.5 active:border-b-2"
        >
          Retry
        </a>
      </div>
    </div>
  );
}
