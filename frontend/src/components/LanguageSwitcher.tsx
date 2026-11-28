'use client'

import { useState, useRef, useEffect } from 'react'
import { useLocale } from 'next-intl'
import { locales, localeNames, localeFlags, type Locale } from '@/i18n/config'
import { useLocaleSwitch } from '@/components/LocaleProvider'
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events'

interface LanguageSwitcherProps {
  variant?: 'default' | 'minimal' | 'auth'
  className?: string
  dropUp?: boolean
}

export default function LanguageSwitcher({
  variant = 'default',
  className = '',
  dropUp = false
}: LanguageSwitcherProps) {
  const currentLocale = useLocale()
  const { switchLocale, prefetchLocale, isSwitching: isPending } = useLocaleSwitch()
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

  const handleLocaleChange = (newLocale: Locale) => {
    setIsOpen(false)
    if (newLocale === currentLocale || isPending) return
    track(ANALYTICS_EVENTS.LANGUAGE_SWITCHED, {
      from: currentLocale,
      to: newLocale,
      surface: window.location.pathname === '/' ? 'landing' : window.location.pathname.split('/')[1],
    })
    // Swaps the text as soon as the messages are in; the server tree
    // catches up in the background, client state survives.
    void switchLocale(newLocale)
  }

  // Warm the other locales' messages so the swap is instant.
  const prefetchOthers = () => {
    for (const locale of locales) if (locale !== currentLocale) prefetchLocale(locale)
  }
  const toggle = () => {
    if (!isOpen) prefetchOthers()
    setIsOpen(!isOpen)
  }

  // Disabled while switching, so a second pick can't race the first.
  const triggerProps = {
    'aria-busy': isPending,
    disabled: isPending,
    onMouseEnter: prefetchOthers,
    onFocus: prefetchOthers,
  }
  const pendingClass = isPending ? ' opacity-60 cursor-wait' : ''

  const currentFlag = localeFlags[currentLocale as Locale] || '🌐'
  const currentName = localeNames[currentLocale as Locale] || currentLocale.toUpperCase()

  if (variant === 'minimal') {
    return (
      <div ref={dropdownRef} className={`relative ${className}`}>
        <button
          onClick={toggle}
        {...triggerProps}
          className={`flex items-center gap-2 px-3 py-2 rounded-xl hover:bg-gray-100 transition-colors text-gray-600${pendingClass}`}
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

  if (variant === 'auth') {
    return (
      <div ref={dropdownRef} className={`relative ${className}`}>
        <button
          onClick={toggle}
        {...triggerProps}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/90 text-gray-800 md:bg-gray-100 md:text-gray-600 hover:bg-white md:hover:bg-gray-200 transition-colors text-sm font-semibold shadow-sm${pendingClass}`}
          aria-label="Change language"
        >
          <span>🌐 {currentLocale === 'kz' ? 'KZ' : currentLocale.toUpperCase()}</span>
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
        onClick={toggle}
        {...triggerProps}
        className={`flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 transition-colors text-white${pendingClass}`}
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
