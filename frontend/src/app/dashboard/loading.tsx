import { INSTANT_LOADING } from '@/lib/feature-flags';

export default function Loading() {
  // When instant loading is enabled, show a minimal stable placeholder
  // that preserves layout dimensions without distracting pulse animations.
  // On subsequent visits, PowerSync renders content from OPFS instantly
  // and this loading state is never visible.
  if (INSTANT_LOADING) {
    return <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white dark:from-[#141414] dark:to-[#141414] p-4 pb-20" />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      <div className="animate-pulse">
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded-lg w-48 mb-2" />
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-6" />
      </div>
      {/* Stats cards */}
      <div className="animate-pulse grid grid-cols-2 gap-3 mb-6">
        <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-20 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
      {/* Course cards */}
      <div className="animate-pulse space-y-4 mb-6">
        <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
      {/* Learning path */}
      <div className="animate-pulse">
        <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-40 mb-3" />
        <div className="h-48 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
    </div>
  );
}
