'use client'

import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect, useState, useRef } from 'react'
import { useTranslations, useLocale } from 'next-intl'
import LoadingScreen from '@/components/LoadingScreen'
import LanguageSwitcher from '@/components/LanguageSwitcher'

// Mascot placeholder component
const MascotPlaceholder = ({ size = 'lg', className = '', label = 'Mascot' }: { size?: 'sm' | 'md' | 'lg' | 'xl', className?: string, label?: string }) => {
  const sizes = {
    sm: 'w-16 h-16',
    md: 'w-24 h-24',
    lg: 'w-32 h-32 md:w-40 md:h-40',
    xl: 'w-48 h-48 md:w-64 md:h-64'
  }

  return (
    <div className={`${sizes[size]} ${className} relative`}>
      <div className="absolute inset-0 bg-gradient-to-br from-purple-400/30 to-indigo-500/30 rounded-3xl border-4 border-dashed border-purple-300/50 flex items-center justify-center backdrop-blur-sm">
        <div className="text-center">
          <img src="/static/images/chesster-logo.png" alt="Chesster" className="w-12 h-12 md:w-16 md:h-16 mx-auto" />
          <p className="text-xs text-purple-200 mt-1 font-medium">{label}</p>
        </div>
      </div>
    </div>
  )
}

// Animated counter component
const AnimatedCounter = ({ target, suffix = '' }: { target: number, suffix?: string }) => {
  const [count, setCount] = useState(0)
  const ref = useRef<HTMLSpanElement>(null)
  const [isVisible, setIsVisible] = useState(false)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true)
        }
      },
      { threshold: 0.5 }
    )

    if (ref.current) {
      observer.observe(ref.current)
    }

    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!isVisible) return

    const duration = 2000
    const steps = 60
    const increment = target / steps
    let current = 0

    const timer = setInterval(() => {
      current += increment
      if (current >= target) {
        setCount(target)
        clearInterval(timer)
      } else {
        setCount(Math.floor(current))
      }
    }, duration / steps)

    return () => clearInterval(timer)
  }, [isVisible, target])

  return <span ref={ref}>{count.toLocaleString()}{suffix}</span>
}

// Feature card with hover animation
const FeatureCard = ({ icon, title, description, delay = 0 }: { icon: string, title: string, description: string, delay?: number }) => {
  const [isVisible, setIsVisible] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setTimeout(() => setIsVisible(true), delay)
        }
      },
      { threshold: 0.2 }
    )

    if (ref.current) {
      observer.observe(ref.current)
    }

    return () => observer.disconnect()
  }, [delay])

  return (
    <div
      ref={ref}
      className={`bg-white rounded-2xl p-6 md:p-8 shadow-lg hover:shadow-2xl transition-all duration-500 transform hover:-translate-y-2 border-b-4 border-purple-500 ${
        isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'
      }`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      <div className="text-5xl mb-4">{icon}</div>
      <h3 className="text-xl font-bold text-gray-800 mb-3 lowercase">{title}</h3>
      <p className="text-gray-600 leading-relaxed">{description}</p>
    </div>
  )
}

// Product card component
const ProductCard = ({ icon, title, description, color, href }: { icon: string, title: string, description: string, color: string, href: string }) => {
  const router = useRouter()

  return (
    <button
      onClick={() => router.push(href)}
      className={`${color} rounded-2xl p-6 text-left hover:scale-105 transition-all duration-300 shadow-lg hover:shadow-2xl group w-full`}
    >
      <div className="text-4xl mb-3 group-hover:scale-110 transition-transform duration-300">{icon}</div>
      <h3 className="text-lg font-bold text-white mb-2">{title}</h3>
      <p className="text-white/80 text-sm">{description}</p>
    </button>
  )
}

export default function HomePage() {
  const { isSignedIn, isLoaded } = useAuth()
  const router = useRouter()
  const [activeFeature, setActiveFeature] = useState(0)
  const t = useTranslations()
  const locale = useLocale()

  // Feature carousel auto-rotate
  useEffect(() => {
    const interval = setInterval(() => {
      setActiveFeature((prev) => (prev + 1) % 4)
    }, 3000)
    return () => clearInterval(interval)
  }, [])

  // Redirect to dashboard if already signed in
  useEffect(() => {
    if (isLoaded && isSignedIn) {
      router.push('/dashboard')
    }
  }, [isLoaded, isSignedIn, router])

  // Show loading animation if not loaded
  if (!isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  // Show loading animation while redirecting
  if (isSignedIn) {
    return <LoadingScreen isVisible={true} />
  }

  const features = [
    { icon: '🧩', label: t('landing.features.puzzles'), description: t('landing.features.puzzlesDesc') },
    { icon: '📖', label: t('landing.features.courses'), description: t('landing.features.coursesDesc') },
    { icon: '🤖', label: t('landing.features.aiAnalysis'), description: t('landing.features.aiAnalysisDesc') },
    { icon: '🎮', label: t('landing.features.play'), description: t('landing.features.playDesc') },
  ]

  const testimonials = [
    { quote: t('landing.testimonials.quote1'), name: t('landing.testimonials.name1'), rating: t('landing.testimonials.rating1') },
    { quote: t('landing.testimonials.quote2'), name: t('landing.testimonials.name2'), rating: t('landing.testimonials.rating2') },
    { quote: t('landing.testimonials.quote3'), name: t('landing.testimonials.name3'), rating: t('landing.testimonials.rating3') },
  ]

  return (
    <>
      {/* Hide the global NavBar on landing page (landing has its own header) + Custom animations */}
      <style dangerouslySetInnerHTML={{ __html: `
        body > nav.bg-white,
        body > nav[class*="bg-white"],
        nav.bg-white.border-b {
          display: none !important;
        }

        @keyframes bounce-slow {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }

        .animate-bounce-slow {
          animation: bounce-slow 3s ease-in-out infinite;
        }

        html { scroll-behavior: smooth; }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #f1f1f1; }
        ::-webkit-scrollbar-thumb { background: #9333ea; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #7c3aed; }
      `}} />

    <main className="min-h-screen bg-white overflow-hidden">
      {/* ===== HEADER (Duolingo-style minimal) ===== */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-sm border-b border-gray-100">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <img src="/static/images/chesster-logo.png" alt="Chesster" className="w-8 h-8 inline" />
            <span className="text-xl font-bold text-gray-800">{t('common.chesster')}</span>
          </div>

          {/* Language/Settings button (Duolingo-style) */}
          <LanguageSwitcher currentLocale={locale} variant="minimal" />
        </div>
      </header>

      {/* ===== HERO SECTION (Duolingo split layout) ===== */}
      <section className="pt-20 min-h-[90vh] flex items-center bg-gradient-to-b from-white to-purple-50">
        <div className="container mx-auto px-4 py-12">
          <div className="flex flex-col lg:flex-row items-center gap-8 lg:gap-16">
            {/* Mascot Side */}
            <div className="flex-1 flex justify-center lg:justify-end order-2 lg:order-1">
              <div className="relative">
                {/* Animated floating effect */}
                <div className="animate-bounce-slow">
                  <MascotPlaceholder size="xl" label={t('landing.mascot')} />
                </div>
                {/* Speech bubble */}
                <div className="absolute -top-4 -right-4 bg-white rounded-2xl px-4 py-2 shadow-lg border-2 border-purple-200 animate-pulse">
                  <span className="text-sm font-bold text-purple-600">{t('landing.letsLearn')} 🎯</span>
                </div>
              </div>
            </div>

            {/* CTA Side */}
            <div className="flex-1 text-center lg:text-left order-1 lg:order-2 max-w-xl">
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-gray-800 mb-6 leading-tight lowercase">
                {t('landing.heroTitle')}
              </h1>

              <p className="text-lg text-gray-600 mb-8">
                {t('landing.heroSubtitle')}
              </p>

              {/* Primary & Secondary CTAs (Duolingo-style stacked buttons) */}
              <div className="flex flex-col gap-4 sm:max-w-sm lg:max-w-md">
                <button
                  onClick={() => router.push('/sign-up')}
                  className="w-full bg-purple-600 hover:bg-purple-700 text-white px-12 py-4 rounded-2xl font-bold text-lg transition-all duration-200 transform hover:scale-105 shadow-lg hover:shadow-xl active:scale-95"
                >
                  {t('common.getStarted')}
                </button>

                {/* Secondary CTA (Duolingo-style bordered button) */}
                <button
                  onClick={() => router.push('/sign-in')}
                  className="w-full bg-white border-2 border-gray-200 border-b-4 hover:bg-gray-50 text-purple-600 px-12 py-4 rounded-2xl font-bold text-lg transition-all duration-200 transform hover:scale-105 active:scale-95 active:border-b-2 shadow-sm hover:shadow-md"
                >
                  {t('landing.alreadyHaveAccount')}
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== FEATURE CAROUSEL (Duolingo language selector style) ===== */}
      <section className="py-8 bg-purple-50 border-y border-purple-100">
        <div className="container mx-auto px-4">
          <div className="flex flex-wrap justify-center gap-4">
            {features.map((feature, index) => (
              <button
                key={feature.label}
                onClick={() => setActiveFeature(index)}
                className={`flex items-center gap-3 px-6 py-3 rounded-2xl transition-all duration-300 ${
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

      {/* ===== VALUE PROPOSITIONS (Duolingo 4-card layout) ===== */}
      <section className="py-20 bg-white">
        <div className="container mx-auto px-4">
          <div className="text-center mb-12">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-800 lowercase mb-4">
              {t('landing.whyWorks.title')}
            </h2>
            <p className="text-gray-600 max-w-2xl mx-auto">
              {t('landing.whyWorks.subtitle')}
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-6xl mx-auto">
            <FeatureCard
              icon="🧠"
              title={t('landing.whyWorks.effective')}
              description={t('landing.whyWorks.effectiveDesc')}
              delay={0}
            />
            <FeatureCard
              icon="🎮"
              title={t('landing.whyWorks.funEngaging')}
              description={t('landing.whyWorks.funEngagingDesc')}
              delay={100}
            />
            <FeatureCard
              icon="📱"
              title={t('landing.whyWorks.personalized')}
              description={t('landing.whyWorks.personalizedDesc')}
              delay={200}
            />
            <FeatureCard
              icon="🆓"
              title={t('landing.whyWorks.free')}
              description={t('landing.whyWorks.freeDesc')}
              delay={300}
            />
          </div>
        </div>
      </section>

      {/* ===== STATS SECTION (Social proof) ===== */}
      <section className="py-16 bg-purple-600 text-white">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 text-center">
            <div>
              <div className="text-4xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={50000} suffix="+" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.activeLearners')}</div>
            </div>
            <div>
              <div className="text-4xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={1000} suffix="+" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.lessons')}</div>
            </div>
            <div>
              <div className="text-4xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={10000} suffix="+" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.puzzles')}</div>
            </div>
            <div>
              <div className="text-4xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={98} suffix="%" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.satisfaction')}</div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== HOW IT WORKS (With mascot) ===== */}
      <section className="py-20 bg-gray-50">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-800 text-center lowercase mb-16">
              {t('landing.howItWorks.title')}
            </h2>

            <div className="space-y-16">
              {/* Step 1 */}
              <div className="flex flex-col md:flex-row items-center gap-8">
                <div className="flex-shrink-0">
                  <MascotPlaceholder size="md" className="transform -rotate-6" label={t('landing.mascot')} />
                </div>
                <div className="flex-1 text-center md:text-left">
                  <div className="inline-flex items-center justify-center w-10 h-10 bg-purple-600 text-white rounded-full font-bold mb-4">1</div>
                  <h3 className="text-2xl font-bold text-gray-800 mb-3">{t('landing.howItWorks.step1Title')}</h3>
                  <p className="text-gray-600">{t('landing.howItWorks.step1Desc')}</p>
                </div>
              </div>

              {/* Step 2 */}
              <div className="flex flex-col md:flex-row-reverse items-center gap-8">
                <div className="flex-shrink-0">
                  <MascotPlaceholder size="md" className="transform rotate-6" label={t('landing.mascot')} />
                </div>
                <div className="flex-1 text-center md:text-right">
                  <div className="inline-flex items-center justify-center w-10 h-10 bg-purple-600 text-white rounded-full font-bold mb-4">2</div>
                  <h3 className="text-2xl font-bold text-gray-800 mb-3">{t('landing.howItWorks.step2Title')}</h3>
                  <p className="text-gray-600">{t('landing.howItWorks.step2Desc')}</p>
                </div>
              </div>

              {/* Step 3 */}
              <div className="flex flex-col md:flex-row items-center gap-8">
                <div className="flex-shrink-0">
                  <MascotPlaceholder size="md" className="transform -rotate-3" label={t('landing.mascot')} />
                </div>
                <div className="flex-1 text-center md:text-left">
                  <div className="inline-flex items-center justify-center w-10 h-10 bg-purple-600 text-white rounded-full font-bold mb-4">3</div>
                  <h3 className="text-2xl font-bold text-gray-800 mb-3">{t('landing.howItWorks.step3Title')}</h3>
                  <p className="text-gray-600">{t('landing.howItWorks.step3Desc')}</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== PRODUCT CARDS (Duolingo-style colorful grid) ===== */}
      <section className="py-20 bg-white">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl md:text-4xl font-bold text-gray-800 text-center lowercase mb-12">
            {t('landing.explore.title')}
          </h2>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 max-w-5xl mx-auto">
            <ProductCard
              icon="📚"
              title={t('landing.explore.coursesTitle')}
              description={t('landing.explore.coursesDesc')}
              color="bg-gradient-to-br from-purple-500 to-purple-700"
              href="/learn"
            />
            <ProductCard
              icon="🧩"
              title={t('landing.explore.puzzlesTitle')}
              description={t('landing.explore.puzzlesDesc')}
              color="bg-gradient-to-br from-indigo-500 to-indigo-700"
              href="/puzzle"
            />
            <ProductCard
              icon="🔬"
              title={t('landing.explore.analysisTitle')}
              description={t('landing.explore.analysisDesc')}
              color="bg-gradient-to-br from-violet-500 to-violet-700"
              href="/position"
            />
            <ProductCard
              icon="🎯"
              title={t('landing.explore.gameReviewTitle')}
              description={t('landing.explore.gameReviewDesc')}
              color="bg-gradient-to-br from-fuchsia-500 to-fuchsia-700"
              href="/game"
            />
          </div>
        </div>
      </section>

      {/* ===== TESTIMONIALS (Social proof) ===== */}
      <section className="py-20 bg-purple-50">
        <div className="container mx-auto px-4">
          <h2 className="text-3xl md:text-4xl font-bold text-gray-800 text-center lowercase mb-12">
            {t('landing.testimonials.title')}
          </h2>

          <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
            {testimonials.map((testimonial, index) => (
              <div key={index} className="bg-white rounded-2xl p-6 shadow-lg">
                <div className="flex items-center gap-3 mb-4">
                  <div className="w-12 h-12 bg-purple-100 rounded-full flex items-center justify-center">
                    <span className="text-xl">👤</span>
                  </div>
                  <div>
                    <div className="font-bold text-gray-800">{testimonial.name}</div>
                    <div className="text-sm text-purple-600">{t('landing.testimonials.ratingLabel')}: {testimonial.rating}</div>
                  </div>
                </div>
                <p className="text-gray-600 italic">&quot;{testimonial.quote}&quot;</p>
                <div className="mt-4 flex gap-1">
                  {[...Array(5)].map((_, i) => (
                    <span key={i} className="text-yellow-400">★</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ===== FINAL CTA (Duolingo-style with mascot) ===== */}
      <section className="py-20 bg-gradient-to-br from-purple-600 to-indigo-700 text-white relative overflow-hidden">
        {/* Background decorations */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute top-10 left-10"><img src="/static/images/chesster-logo.png" alt="" className="w-24 h-24 opacity-20" /></div>
          <div className="absolute bottom-10 right-10 text-9xl">♞</div>
          <div className="absolute top-1/2 left-1/4 text-6xl">♜</div>
          <div className="absolute top-1/3 right-1/4 text-7xl">♛</div>
        </div>

        <div className="container mx-auto px-4 relative z-10">
          <div className="flex flex-col lg:flex-row items-center justify-center gap-12 max-w-4xl mx-auto">
            {/* Mascot */}
            <div className="flex-shrink-0">
              <MascotPlaceholder size="lg" label={t('landing.mascot')} />
            </div>

            {/* CTA Content */}
            <div className="text-center lg:text-left">
              <h2 className="text-3xl md:text-4xl lg:text-5xl font-bold mb-6 lowercase">
                {t('landing.cta.title')}
              </h2>
              <p className="text-xl text-purple-200 mb-8">
                {t('landing.cta.subtitle')}
              </p>

              <button
                onClick={() => router.push('/sign-up')}
                className="bg-white text-purple-600 hover:bg-purple-50 px-12 py-4 rounded-2xl font-bold text-lg transition-all duration-200 transform hover:scale-105 shadow-xl hover:shadow-2xl active:scale-95"
              >
                {t('landing.cta.button')}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="bg-gray-900 text-gray-400 py-12">
        <div className="container mx-auto px-4">
          <div className="grid md:grid-cols-4 gap-8 mb-8">
            {/* Brand */}
            <div>
              <div className="flex items-center gap-2 mb-4">
                <img src="/static/images/chesster-logo.png" alt="Chesster" className="w-8 h-8 inline" />
                <span className="text-xl font-bold text-white">{t('common.chesster')}</span>
              </div>
              <p className="text-sm">{t('landing.footer.tagline')}</p>
            </div>

            {/* Products */}
            <div>
              <h4 className="text-white font-bold mb-4">{t('landing.footer.products')}</h4>
              <ul className="space-y-2 text-sm">
                <li><button onClick={() => router.push('/learn')} className="hover:text-white transition-colors">{t('landing.footer.courses')}</button></li>
                <li><button onClick={() => router.push('/puzzle')} className="hover:text-white transition-colors">{t('landing.footer.puzzles')}</button></li>
                <li><button onClick={() => router.push('/position')} className="hover:text-white transition-colors">{t('landing.footer.analysis')}</button></li>
                <li><button onClick={() => router.push('/game')} className="hover:text-white transition-colors">{t('landing.footer.gameReview')}</button></li>
              </ul>
            </div>

            {/* Company */}
            <div>
              <h4 className="text-white font-bold mb-4">{t('landing.footer.company')}</h4>
              <ul className="space-y-2 text-sm">
                <li><button className="hover:text-white transition-colors">{t('landing.footer.about')}</button></li>
                <li><button className="hover:text-white transition-colors">{t('landing.footer.careers')}</button></li>
                <li><button className="hover:text-white transition-colors">{t('landing.footer.blog')}</button></li>
                <li><button className="hover:text-white transition-colors">{t('landing.footer.press')}</button></li>
              </ul>
            </div>

            {/* Social */}
            <div>
              <h4 className="text-white font-bold mb-4">{t('landing.footer.connect')}</h4>
              <div className="flex gap-4">
                <button className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors">
                  <span>𝕏</span>
                </button>
                <button className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors">
                  <span>📸</span>
                </button>
                <button className="w-10 h-10 bg-gray-800 rounded-full flex items-center justify-center hover:bg-gray-700 transition-colors">
                  <span>▶️</span>
                </button>
              </div>
            </div>
          </div>

          <div className="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-sm">{t('landing.footer.copyright')}</p>
            <div className="flex gap-6 text-sm">
              <button className="hover:text-white transition-colors">{t('landing.footer.privacy')}</button>
              <button className="hover:text-white transition-colors">{t('landing.footer.terms')}</button>
              <button className="hover:text-white transition-colors">{t('landing.footer.cookies')}</button>
            </div>
          </div>
        </div>
      </footer>

    </main>
    </>
  )
}
