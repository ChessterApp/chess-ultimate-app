'use client'

import { SignUp } from '@clerk/nextjs'
import { useTranslations } from 'next-intl'
import Image from 'next/image'

export default function SignUpPage() {
  const t = useTranslations()

  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)] overflow-x-hidden">
      {/* Hide default Clerk branding and apply Duolingo-style design */}
      <style dangerouslySetInnerHTML={{ __html: `
        /* Hide Clerk branding */
        .cl-internal-b3fm6y,
        .cl-footerActionLink,
        [data-localization-key="signUp.start.actionLink"] {
          display: none !important;
        }

        /* Card container */
        .cl-card {
          background: white !important;
          box-shadow: none !important;
          border: none !important;
          padding: 1rem !important;
          max-width: 100% !important;
          width: 100% !important;
          overflow: hidden !important;
          box-sizing: border-box !important;
          margin: 0 !important;
        }

        /* Hide Clerk header — we use our own */
        .cl-header {
          display: none !important;
        }

        /* Input fields - Duolingo style rounded */
        .cl-formFieldInput {
          border: 2px solid #e5e5e5 !important;
          border-radius: 16px !important;
          padding: 16px 18px !important;
          font-size: 1rem !important;
          background: white !important;
          color: #3c3c3c !important;
          height: auto !important;
          min-height: 56px !important;
          transition: border-color 0.2s ease !important;
        }

        .cl-formFieldInput:focus {
          border-color: #1cb0f6 !important;
          box-shadow: none !important;
          outline: none !important;
        }

        .cl-formFieldInput::placeholder {
          color: #afafaf !important;
        }

        /* Form field labels */
        .cl-formFieldLabel {
          display: none !important;
        }

        /* Form field wrapper - tight spacing like Duolingo */
        .cl-formFieldRow {
          margin-bottom: 4px !important;
        }

        /* Form container - reduce overall gaps */
        .cl-form {
          gap: 4px !important;
        }

        /* Password visibility toggle */
        .cl-formFieldInputShowPasswordButton {
          color: #afafaf !important;
          right: 16px !important;
        }

        /* Primary button - Duolingo style */
        .cl-formButtonPrimary {
          background: linear-gradient(to bottom, #9333ea, #7c3aed) !important;
          border: none !important;
          border-bottom: 4px solid #6b21a8 !important;
          border-radius: 16px !important;
          padding: 14px 24px !important;
          font-size: 0.875rem !important;
          font-weight: 700 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.8px !important;
          color: white !important;
          min-height: 54px !important;
          transition: all 0.15s ease !important;
          margin-top: 8px !important;
        }

        .cl-formButtonPrimary:hover {
          background: linear-gradient(to bottom, #a855f7, #8b5cf6) !important;
          transform: translateY(-1px) !important;
        }

        .cl-formButtonPrimary:active {
          border-bottom-width: 2px !important;
          transform: translateY(2px) !important;
        }

        /* Divider - "OR" */
        .cl-dividerRow {
          margin: 20px 0 !important;
        }

        .cl-dividerLine {
          background: #e5e5e5 !important;
        }

        .cl-dividerText {
          color: #afafaf !important;
          font-size: 0.875rem !important;
          font-weight: 600 !important;
          text-transform: uppercase !important;
        }

        /* Social buttons container */
        .cl-socialButtons {
          gap: 12px !important;
        }

        /* Social buttons - Duolingo style */
        .cl-socialButtonsBlockButton {
          border: 2px solid #e5e5e5 !important;
          border-radius: 16px !important;
          padding: 12px 16px !important;
          background: white !important;
          min-height: 50px !important;
          transition: all 0.2s ease !important;
          flex: 1 !important;
        }

        .cl-socialButtonsBlockButton:hover {
          background: #f7f7f7 !important;
          border-color: #d5d5d5 !important;
        }

        .cl-socialButtonsBlockButtonText {
          font-size: 0.875rem !important;
          font-weight: 700 !important;
          color: #3c3c3c !important;
          text-transform: uppercase !important;
        }

        .cl-socialButtonsIconButton {
          border: 2px solid #e5e5e5 !important;
          border-radius: 16px !important;
          padding: 12px 20px !important;
          background: white !important;
          min-height: 50px !important;
          min-width: 120px !important;
          transition: all 0.2s ease !important;
        }

        .cl-socialButtonsIconButton:hover {
          background: #f7f7f7 !important;
          border-color: #d5d5d5 !important;
        }

        /* Social buttons provider icons */
        .cl-socialButtonsProviderIcon {
          width: 20px !important;
          height: 20px !important;
        }

        /* Footer area */
        .cl-footer {
          margin-top: 24px !important;
        }

        .cl-footerAction {
          justify-content: center !important;
        }

        .cl-footerActionText {
          color: #afafaf !important;
          font-size: 0.875rem !important;
        }

        /* Root box */
        .cl-rootBox {
          width: 100% !important;
          max-width: 100% !important;
          margin: 0 auto !important;
        }

        /* Form container */
        .cl-form {
          gap: 0 !important;
        }

        /* Error messages */
        .cl-formFieldErrorText {
          color: #ff4b4b !important;
          font-size: 0.75rem !important;
          margin-top: 4px !important;
        }

        /* Hide "Secured by Clerk" and all Clerk footers */
        .cl-internal-1dauvpw,
        .cl-internal-mxmka,
        [aria-label*="Clerk"],
        .cl-footerPages,
        .cl-footerPagesLink,
        .cl-footer,
        .cl-footerAction,
        .cl-footerActionText,
        .cl-footerActionLink {
          display: none !important;
        }

        /* Card box - prevent overflow */
        .cl-cardBox {
          width: 100% !important;
          max-width: 100% !important;
          margin: 0 !important;
          border: none !important;
          box-shadow: none !important;
        }

        /* Alternative sign-in text */
        .cl-footerActionLink__signIn {
          color: #1cb0f6 !important;
          font-weight: 700 !important;
          text-decoration: none !important;
        }

        .cl-footerActionLink__signIn:hover {
          text-decoration: underline !important;
        }

        /* Main internal content wrapper */
        .cl-main {
          padding: 0 !important;
        }

        /* Adjustments for layout */
        .cl-socialButtonsBlockButtonText__google,
        .cl-socialButtonsBlockButtonText__apple {
          text-transform: uppercase !important;
        }

        /* Hide Last Name field */
        .cl-formFieldRow__lastName,
        [data-field-id="lastName"],
        .cl-formField__lastName {
          display: none !important;
        }

        /* Make First Name field full width when Last Name is hidden */
        .cl-formFieldRow__firstName,
        [data-field-id="firstName"],
        .cl-formField__firstName {
          width: 100% !important;
          flex: 1 !important;
        }

        /* Hide the name row grid that contains both fields */
        .cl-formFieldRow:has(.cl-formField__lastName) {
          display: block !important;
        }
      `}} />

      <div className="w-full max-w-sm bg-white md:bg-transparent rounded-3xl md:rounded-none p-4 md:p-0 mt-4 md:mt-0 shadow-xl md:shadow-none overflow-hidden">
        {/* Optional: Add Chesster branding above the form */}
        <div className="text-center mb-4 md:mb-6">
          <div className="bg-white rounded-full p-3 md:p-4 inline-block shadow-lg"><Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={64} height={64} className="w-10 h-10 md:w-16 md:h-16" /></div>
          <h1 className="text-2xl font-bold text-gray-800 mt-4">{t('auth.signUpTitle')}</h1>
          <p className="text-sm text-gray-500 mt-1">{t('auth.signUpSubtitle')}</p>
        </div>

        <SignUp
          appearance={{
            layout: {
              socialButtonsPlacement: 'bottom',
              socialButtonsVariant: 'blockButton',
              termsPageUrl: '/terms',
              privacyPageUrl: '/privacy',
            },
            variables: {
              colorPrimary: '#9333ea',
              colorText: '#3c3c3c',
              colorTextSecondary: '#afafaf',
              colorBackground: '#ffffff',
              colorInputBackground: '#ffffff',
              colorInputText: '#3c3c3c',
              borderRadius: '16px',
              fontFamily: 'inherit',
            },
            elements: {
              rootBox: 'w-full',
              card: 'shadow-none border-0 bg-white p-8 rounded-3xl',
              headerTitle: 'text-2xl font-bold text-gray-800 text-center',
              headerSubtitle: 'text-sm text-gray-500 text-center',
              formFieldInput: 'rounded-2xl border-2 border-gray-200 py-4 px-5 text-base focus:border-purple-500',
              formFieldLabel: 'hidden',
              formButtonPrimary: 'bg-purple-600 hover:bg-purple-700 rounded-2xl py-4 font-bold uppercase tracking-wide border-b-4 border-purple-800 active:border-b-2 active:translate-y-0.5 transition-all',
              socialButtonsBlockButton: 'border-2 border-gray-200 rounded-2xl py-3 hover:bg-gray-50 transition-colors',
              socialButtonsBlockButtonText: 'font-bold uppercase text-sm text-gray-700',
              dividerLine: 'bg-gray-200',
              dividerText: 'text-gray-400 uppercase font-semibold text-sm',
              footer: 'hidden',
              footerAction: 'hidden',
            },
          }}
        />

        {/* Custom footer with sign-in link */}
        <div className="text-center mt-4">
          <span className="text-gray-400 text-sm">{t('auth.haveAccount')} </span>
          <a href="/sign-in" className="text-purple-600 font-bold text-sm hover:underline">
            {t('common.signIn')}
          </a>
        </div>
      </div>

    </div>
  )
}
