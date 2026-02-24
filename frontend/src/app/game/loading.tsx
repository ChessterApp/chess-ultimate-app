export default function Loading() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      <div className="animate-pulse">
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded-lg w-48 mb-6" />
      </div>
      {/* Input cards */}
      <div className="animate-pulse space-y-4">
        <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded-xl" />
      </div>
    </div>
  );
}
