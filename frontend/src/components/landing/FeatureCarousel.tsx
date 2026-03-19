'use client'

import { useEffect, useState } from 'react'

interface Feature {
  icon: string
  label: string
  description: string
}

export function FeatureCarousel({ features }: { features: Feature[] }) {
  const [activeFeature, setActiveFeature] = useState(0)

  // Feature carousel auto-rotate
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveFeature((prev) => (prev + 1) % features.length)
    }, 3000)
    return () => clearInterval(interval)
  }, [features.length])

  return (
    <section className="py-8 bg-purple-50 border-y border-purple-100 hidden lg:block">
      <div className="container mx-auto px-4">
        <div className="flex overflow-x-auto gap-3 pb-2 snap-x snap-mandatory px-2 -mx-2 scrollbar-hide">
          {features.map((feature, index) => (
            <button
              key={feature.label}
              onClick={() => setActiveFeature(index)}
              className={`flex-shrink-0 snap-start flex items-center gap-3 px-6 py-3 rounded-2xl transition-all duration-300 ${
                activeFeature === index
                  ? 'bg-purple-600 text-white shadow-lg scale-105'
                  : 'bg-white text-gray-700 hover:bg-purple-100'
              }`}
            >
              <span className="text-2xl">{feature.icon}</span>
              <div className="text-left">
                <div className="font-bold text-sm">{feature.label}</div>
                <div className={`text-xs ${activeFeature === index ? 'text-purple-200' : 'text-gray-500'}`}>
                  {feature.description}
                </div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  )
}
