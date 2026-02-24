export default function Loading() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      <div className="animate-pulse">
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded-lg w-40 mb-2" />
        <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-64 mb-6" />
      </div>
      {/* Course cards */}
      <div className="animate-pulse space-y-4">
        <div className="h-28 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-28 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-28 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-28 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
    </div>
  );
}
