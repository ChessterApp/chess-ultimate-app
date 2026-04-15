import { INSTANT_LOADING } from '@/lib/feature-flags';

export default function Loading() {
  if (INSTANT_LOADING) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-[#141414] pb-24">
        <div className="bg-gradient-to-br from-purple-600 to-purple-800 h-[76px]" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="container mx-auto px-4 py-6">
          <div className="animate-pulse flex items-center gap-3">
            <div className="w-9 h-9 bg-white/20 rounded-xl" />
            <div>
              <div className="h-7 bg-white/20 rounded w-32 mb-1" />
              <div className="h-4 bg-white/10 rounded w-48" />
            </div>
          </div>
        </div>
      </div>
      <div className="container mx-auto px-4 py-6 space-y-6">
        <div className="animate-pulse bg-white rounded-2xl shadow-md p-6">
          <div className="h-6 bg-gray-200 rounded w-36 mb-4" />
          <div className="grid grid-cols-3 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="aspect-square bg-gray-200 rounded-xl" />
            ))}
          </div>
        </div>
        <div className="animate-pulse bg-white rounded-2xl shadow-md p-6">
          <div className="h-6 bg-gray-200 rounded w-32 mb-4" />
          <div className="grid grid-cols-3 gap-3">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-20 bg-gray-200 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
