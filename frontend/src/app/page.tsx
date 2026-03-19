import { useTranslations, useLocale } from 'next-intl'
import Image from 'next/image'
import LanguageSwitcher from '@/components/LanguageSwitcher'
import { LandingPageRedirect } from '@/components/landing/LandingPageClient'
import { AnimatedCounter } from '@/components/landing/AnimatedCounter'
import { FeatureCard } from '@/components/landing/FeatureCard'
import { ProductCard } from '@/components/landing/ProductCard'
import { HeroButtons } from '@/components/landing/HeroButtons'
import { FeatureCarousel } from '@/components/landing/FeatureCarousel'
import { TestimonialsSection } from '@/components/landing/TestimonialsSection'
import { FooterButton } from '@/components/landing/FooterButtons'
import { CTAButton } from '@/components/landing/CTAButton'
import { HeroAnimatedBackground } from '@/components/landing/HeroAnimatedBackground'
import { SocialButtons } from '@/components/landing/SocialButtons'

// Enable ISR: regenerate page every hour
export const revalidate = 3600

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
          <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={64} height={64} className="w-12 h-12 md:w-16 md:h-16 mx-auto" />
          <p className="text-xs text-purple-200 mt-1 font-medium">{label}</p>
        </div>
      </div>
    </div>
  )
}

export default function HomePage() {
  const t = useTranslations()
  const locale = useLocale()

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
    { quote: t('landing.testimonials.quote4'), name: t('landing.testimonials.name4'), rating: t('landing.testimonials.rating4') },
    { quote: t('landing.testimonials.quote5'), name: t('landing.testimonials.name5'), rating: t('landing.testimonials.rating5') },
    { quote: t('landing.testimonials.quote6'), name: t('landing.testimonials.name6'), rating: t('landing.testimonials.rating6') },
  ]

  return (
    <>
      {/* Client island: handles redirect to dashboard if user is signed in */}
      <LandingPageRedirect />

      {/* Main HTML structure: rendered as server component for instant pre-rendering */}
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

        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }

        @supports(padding: env(safe-area-inset-bottom)) {
          main { padding-bottom: env(safe-area-inset-bottom); }
        }
      `}} />

    <main className="min-h-screen bg-white overflow-hidden">
      {/* ===== HEADER (Duolingo-style minimal) ===== */}
      <header className="fixed top-0 left-0 right-0 z-50 bg-transparent lg:bg-white/95 lg:backdrop-blur-sm lg:border-b lg:border-gray-100">
        <div className="container mx-auto px-4 py-3 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2">
            <div className="bg-white rounded-full p-1"><Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={32} height={32} className="w-6 h-6 inline" /></div>
            <span className="text-xl font-bold text-white lg:text-gray-800">{t('common.chesster')}</span>
          </div>

          {/* Language/Settings button (Duolingo-style) */}
          <LanguageSwitcher currentLocale={locale} variant="minimal" />
        </div>
      </header>

      {/* ===== HERO SECTION (Redesigned — gradient bg, prominent mascot, subtle animation) ===== */}
      <section className="pt-20 min-h-[100dvh] lg:min-h-[90vh] flex items-center relative overflow-hidden bg-purple-600 lg:bg-gradient-to-br lg:from-purple-700 lg:via-indigo-600 lg:to-violet-800">
        {/* Animated background shapes */}
        <HeroAnimatedBackground />

        <div className="container mx-auto px-6 py-8 relative z-10 h-full">
          {/* Mobile: vertical layout — mascot top, text middle, CTAs bottom */}
          <div className="flex flex-col items-center justify-center gap-6 min-h-[calc(100dvh-5rem)] lg:min-h-0 lg:flex-row lg:items-center lg:gap-16">
            {/* Mascot */}
            <div className="flex-shrink-0 flex justify-center lg:flex-1 lg:justify-end pt-4 lg:pt-0 lg:order-1">
              <div className="relative">
                <div className="absolute inset-0 -m-8 bg-gradient-to-br from-purple-400/30 to-indigo-300/20 rounded-full blur-2xl" />
                <div className="animate-bounce-slow relative">
                  <div className="bg-white rounded-full p-5 lg:p-6 shadow-xl">
                    <Image
                      src="/static/images/chesster-logo-v3.png"
                      alt="Chesster"
                      width={280}
                      height={280}
                      className="w-36 h-36 md:w-40 md:h-40 lg:w-60 lg:h-60"
                      priority
                    />
                  </div>
                </div>
                <div className="hidden md:block absolute -top-2 -right-2 md:-top-4 md:-right-4 bg-white rounded-2xl px-4 py-2 shadow-lg border-2 border-purple-200 animate-pulse">
                  <span className="text-sm font-bold text-purple-600">{t('landing.letsLearn')} 🎯</span>
                </div>
              </div>
            </div>

            {/* Text + CTAs */}
            <div className="flex-1 text-center lg:text-left lg:order-2 max-w-xl flex flex-col items-center lg:items-start">
              <h1 className="text-3xl sm:text-4xl lg:text-7xl font-extrabold text-white mb-3 lg:mb-6 leading-[1.1] lowercase tracking-tight">
                <span className="bg-gradient-to-r from-white via-purple-100 to-indigo-200 bg-clip-text text-transparent">
                  {t('landing.heroTitle')}
                </span>
              </h1>

              <p className="text-base md:text-xl text-purple-100/90 mb-6 lg:mb-8 leading-relaxed">
                {t('landing.heroSubtitle')}
              </p>

              <HeroButtons />
            </div>
          </div>
        </div>

        {/* Wave divider */}
        <div className="absolute bottom-0 left-0 right-0 hidden lg:block">
          <svg viewBox="0 0 1440 80" fill="none" xmlns="http://www.w3.org/2000/svg" className="w-full">
            <path d="M0,40 C360,80 720,0 1080,40 C1260,60 1380,50 1440,40 L1440,80 L0,80 Z" fill="#faf5ff" />
          </svg>
        </div>
      </section>

      {/* ===== FEATURE CAROUSEL (Duolingo language selector style) ===== */}
      <FeatureCarousel features={features} />

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
            <div className="hidden sm:block"><FeatureCard
              icon="📱"
              title={t('landing.whyWorks.personalized')}
              description={t('landing.whyWorks.personalizedDesc')}
              delay={200}
            /></div>
            <div className="hidden sm:block"><FeatureCard
              icon="🆓"
              title={t('landing.whyWorks.free')}
              description={t('landing.whyWorks.freeDesc')}
              delay={300}
            /></div>
          </div>
        </div>
      </section>

      {/* ===== STATS SECTION (Social proof) ===== */}
      <section className="py-16 bg-purple-600 text-white">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-8 text-center">
            <div>
              <div className="text-2xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={50000} suffix="+" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.activeLearners')}</div>
            </div>
            <div>
              <div className="text-2xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={1000} suffix="+" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.lessons')}</div>
            </div>
            <div>
              <div className="text-2xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={10000} suffix="+" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.puzzles')}</div>
            </div>
            <div>
              <div className="text-2xl md:text-5xl font-bold mb-2">
                <AnimatedCounter target={98} suffix="%" />
              </div>
              <div className="text-purple-200 font-medium">{t('landing.stats.satisfaction')}</div>
            </div>
          </div>
        </div>
      </section>

      {/* ===== HOW IT WORKS (With mascot) ===== */}
      <section className="py-20 bg-gray-50 hidden lg:block">
        <div className="container mx-auto px-4">
          <div className="max-w-4xl mx-auto">
            <h2 className="text-3xl md:text-4xl font-bold text-gray-800 text-center lowercase mb-16">
              {t('landing.howItWorks.title')}
            </h2>

            <div className="space-y-16">
              {/* Step 1 */}
              <div className="flex flex-col md:flex-row items-center gap-8">
                <div className="flex-shrink-0 hidden md:block">
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
                <div className="flex-shrink-0 hidden md:block">
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
                <div className="flex-shrink-0 hidden md:block">
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
      <section className="py-20 bg-white hidden lg:block">
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
      <TestimonialsSection testimonials={testimonials} />

      {/* ===== FINAL CTA (Duolingo-style with mascot) ===== */}
      <section className="py-20 bg-gradient-to-br from-purple-600 to-indigo-700 text-white relative overflow-hidden">
        {/* Background decorations */}
        <div className="absolute inset-0 opacity-10 hidden lg:block">
          <div className="absolute top-10 left-10"><Image src="/static/images/chesster-logo-v3.png" alt="" width={96} height={96} className="w-24 h-24 opacity-20" loading="lazy" /></div>
          <div className="absolute bottom-10 right-10 text-9xl">♞</div>
          <div className="absolute top-1/2 left-1/4 text-6xl">♜</div>
          <div className="absolute top-1/3 right-1/4 text-7xl">♛</div>
        </div>

        <div className="container mx-auto px-4 relative z-10">
          <div className="flex flex-col lg:flex-row items-center justify-center gap-12 max-w-4xl mx-auto">
            {/* Mascot */}
            <div className="flex-shrink-0 hidden lg:block">
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

              <CTAButton
                href="/sign-up"
                className="bg-white text-purple-600 hover:bg-purple-50 px-12 py-4 rounded-2xl font-bold text-lg transition-all duration-200 transform hover:scale-105 shadow-xl hover:shadow-2xl active:scale-95"
              >
                {t('landing.cta.button')}
              </CTAButton>
            </div>
          </div>
        </div>
      </section>

      {/* ===== FOOTER ===== */}
      <footer className="bg-gray-900 text-gray-400 py-12">
        <div className="container mx-auto px-4">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 md:gap-8 mb-8">
            {/* Brand */}
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="bg-white rounded-full p-1"><Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={32} height={32} className="w-6 h-6 inline" /></div>
                <span className="text-xl font-bold text-white">{t('common.chesster')}</span>
              </div>
              <p className="text-sm">{t('landing.footer.tagline')}</p>
            </div>

            {/* Products */}
            <div>
              <h4 className="text-white font-bold mb-4">{t('landing.footer.products')}</h4>
              <ul className="space-y-2 text-sm">
                <li><FooterButton href="/learn">{t('landing.footer.courses')}</FooterButton></li>
                <li><FooterButton href="/puzzle">{t('landing.footer.puzzles')}</FooterButton></li>
                <li><FooterButton href="/position">{t('landing.footer.analysis')}</FooterButton></li>
                <li><FooterButton href="/game">{t('landing.footer.gameReview')}</FooterButton></li>
              </ul>
            </div>

            {/* Company */}
            <div className="hidden md:block">
              <h4 className="text-white font-bold mb-4">{t('landing.footer.company')}</h4>
              <ul className="space-y-2 text-sm">
                <li><FooterButton>{t('landing.footer.about')}</FooterButton></li>
                <li><FooterButton>{t('landing.footer.careers')}</FooterButton></li>
                <li><FooterButton>{t('landing.footer.blog')}</FooterButton></li>
                <li><FooterButton>{t('landing.footer.press')}</FooterButton></li>
              </ul>
            </div>

            {/* Social */}
            <div className="hidden md:block">
              <h4 className="text-white font-bold mb-4">{t('landing.footer.connect')}</h4>
              <SocialButtons />
            </div>
          </div>

          <div className="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center gap-4">
            <p className="text-sm">{t('landing.footer.copyright')}</p>
            <div className="flex gap-6 text-sm">
              <FooterButton>{t('landing.footer.privacy')}</FooterButton>
              <FooterButton>{t('landing.footer.terms')}</FooterButton>
              <FooterButton>{t('landing.footer.cookies')}</FooterButton>
            </div>
          </div>
        </div>
      </footer>

    </main>
    </>
  )
}
