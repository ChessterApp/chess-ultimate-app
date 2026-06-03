'use client'

import { useState, useRef, useEffect } from 'react'
import { locales, localeNames, localeFlags, type Locale } from '@/i18n/config'
import { setLocale } from '@/app/actions/setLocale'

interface LanguageSwitcherProps {
  currentLocale: string
  variant?: 'default' | 'minimal'
  className?: string
  dropUp?: boolean
}

export default function LanguageSwitcher({
  currentLocale,
  variant = 'default',
  className = '',
  dropUp = false
}: LanguageSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleLocaleChange = async (newLocale: Locale) => {
    // Use server action to ensure cookie is set properly
    await setLocale(newLocale)
    setIsOpen(false)
    // Full reload so client components consuming NextIntlClientProvider re-mount with the new messages
    window.location.reload()
  }

  const currentFlag = localeFlags[currentLocale as Locale] || '🌐'
  const currentName = localeNames[currentLocale as Locale] || currentLocale.toUpperCase()

  if (variant === 'minimal') {
    return (
      <div ref={dropdownRef} className={`relative ${className}`}>
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-gray-100 transition-colors text-gray-600"
          aria-label="Change language"
        >
          <span className="text-sm font-semibold">🌐 {currentLocale === 'kz' ? 'KZ' : currentLocale.toUpperCase()}</span>
        </button>

        {isOpen && (
          <div className={`absolute ${dropUp ? 'bottom-full mb-2' : 'top-full mt-2'} right-0 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-50`}>
            {locales.map((locale) => (
              <button
                key={locale}
                onClick={() => handleLocaleChange(locale)}
                className={`w-full flex items-center justify-center px-3 py-2 hover:bg-purple-50 transition-colors ${
                  currentLocale === locale ? 'bg-purple-100' : ''
                }`}
              >
                <span className="text-xl">{localeFlags[locale]}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors text-white"
        aria-label="Change language"
      >
        <span className="text-lg">{currentFlag}</span>
        <span className="font-medium">{currentName}</span>
        <svg
          className={`w-4 h-4 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-2 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-50 min-w-[160px]">
          {locales.map((locale) => (
            <button
              key={locale}
              onClick={() => handleLocaleChange(locale)}
              className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-purple-50 transition-colors ${
                currentLocale === locale ? 'bg-purple-100 text-purple-700' : 'text-gray-700'
              }`}
            >
              <span className="text-lg">{localeFlags[locale]}</span>
              <span className="font-medium">{localeNames[locale]}</span>
              {currentLocale === locale && (
                <svg className="w-4 h-4 ml-auto text-purple-600" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
