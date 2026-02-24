export default function Loading() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      {/* Profile header */}
      <div className="animate-pulse flex items-center gap-4 mb-6">
        <div className="h-16 w-16 bg-gray-200 dark:bg-gray-700 rounded-full" />
        <div className="space-y-2">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-36" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-48" />
        </div>
      </div>
      {/* Stats grid */}
      <div className="animate-pulse grid grid-cols-2 gap-3 mb-6">
        <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
      {/* Achievements */}
      <div className="animate-pulse space-y-3">
        <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-32 mb-3" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
    </div>
  );
}
