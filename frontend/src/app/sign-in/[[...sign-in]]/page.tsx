'use client'

import { SignIn } from '@clerk/nextjs'
import { useTranslations } from 'next-intl'
import Image from 'next/image'
import { useBranding, useOrganization } from '@/contexts/OrganizationContext'

export default function SignInPage() {
  const t = useTranslations()
  const branding = useBranding()
  const { isWhiteLabel } = useOrganization()
  const heading = isWhiteLabel
    ? `${t('auth.signInTitle')} · ${branding.name}`
    : t('auth.signInTitle')

  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)]">
      {/* Hide default Clerk branding and apply Duolingo-style design */}
      <style dangerouslySetInnerHTML={{ __html: `
        /* Hide Clerk branding */
        .cl-internal-b3fm6y,
        .cl-footerActionLink,
        [data-localization-key="signIn.start.actionLink"] {
          display: none !important;
        }

        /* Card container */
        .cl-card {
          background: var(--surface-card, #FFFFFF) !important;
          box-shadow: none !important;
          border: none !important;
          padding: 1rem !important;
          max-width: 100% !important;
          width: 100% !important;
          overflow: visible !important;
          box-sizing: border-box !important;
          margin: 0 !important;
        }

        /* Hide Clerk header — we use our own */
        .cl-header {
          display: none !important;
        }

        /* Input fields - Duolingo style rounded */
        .cl-formFieldInput {
          border: 2px solid var(--border-default, #E4E4E7) !important;
          border-radius: 16px !important;
          padding: 16px 18px !important;
          font-size: 1rem !important;
          background: var(--surface-input, #FFFFFF) !important;
          color: var(--text-primary, #18181B) !important;
          height: auto !important;
          min-height: 56px !important;
          transition: border-color 0.2s ease !important;
        }

        .cl-formFieldInput:focus {
          border-color: var(--primary, #8B5CF6) !important;
          box-shadow: none !important;
          outline: none !important;
        }

        .cl-formFieldInput::placeholder {
          color: var(--text-tertiary, #A1A1AA) !important;
        }

        /* Form field labels */
        .cl-formFieldLabel {
          display: none !important;
        }

        /* Form field wrapper */
        .cl-formFieldRow {
          margin-bottom: 12px !important;
        }

        /* Password visibility toggle */
        .cl-formFieldInputShowPasswordButton {
          color: var(--text-tertiary, #A1A1AA) !important;
          right: 16px !important;
        }

        /* Primary button - Duolingo style */
        .cl-formButtonPrimary {
          background: linear-gradient(to bottom, var(--primary, #8B5CF6), var(--primary-hover, #7C3AED)) !important;
          border: none !important;
          border-bottom: 4px solid var(--primary-hover, #7C3AED) !important;
          border-radius: 16px !important;
          padding: 14px 24px !important;
          font-size: 0.875rem !important;
          font-weight: 700 !important;
          text-transform: uppercase !important;
          letter-spacing: 0.8px !important;
          color: var(--text-on-primary, #FFFFFF) !important;
          min-height: 54px !important;
          transition: all 0.15s ease !important;
          margin-top: 8px !important;
        }

        .cl-formButtonPrimary:hover {
          background: linear-gradient(to bottom, var(--primary-light-hover, #a855f7), var(--primary, #8B5CF6)) !important;
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
          background: var(--border-default, #E4E4E7) !important;
        }

        .cl-dividerText {
          color: var(--text-tertiary, #A1A1AA) !important;
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
          border: 2px solid var(--border-default, #E4E4E7) !important;
          border-radius: 16px !important;
          padding: 12px 16px !important;
          background: var(--surface-card, #FFFFFF) !important;
          min-height: 50px !important;
          transition: all 0.2s ease !important;
          flex: 1 !important;
        }

        .cl-socialButtonsBlockButton:hover {
          background: var(--surface-card-hover, #F4F4F5) !important;
          border-color: var(--border-strong, #D4D4D8) !important;
        }

        .cl-socialButtonsBlockButtonText {
          font-size: 0.875rem !important;
          font-weight: 700 !important;
          color: var(--text-primary, #18181B) !important;
          text-transform: uppercase !important;
        }

        .cl-socialButtonsIconButton {
          border: 2px solid var(--border-default, #E4E4E7) !important;
          border-radius: 16px !important;
          padding: 12px 20px !important;
          background: var(--surface-card, #FFFFFF) !important;
          min-height: 50px !important;
          min-width: 120px !important;
          transition: all 0.2s ease !important;
        }

        .cl-socialButtonsIconButton:hover {
          background: var(--surface-card-hover, #F4F4F5) !important;
          border-color: var(--border-strong, #D4D4D8) !important;
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
          color: var(--text-tertiary, #A1A1AA) !important;
          font-size: 0.875rem !important;
        }

        /* Root box */
        .cl-rootBox {
          width: 100% !important;
          max-width: 100% !important;
          margin: 0 auto !important;
        }

        /* Card box - prevent overflow */
        .cl-cardBox {
          width: 100% !important;
          max-width: 100% !important;
          margin: 0 !important;
          border: none !important;
          box-shadow: none !important;
        }

        /* Form container */
        .cl-form {
          gap: 0 !important;
        }

        /* OTP Verification - Mobile responsive styles */
        .cl-otpCodeFieldInput {
          min-width: 40px !important;
          min-height: 40px !important;
          width: 48px !important;
          height: 48px !important;
          font-size: 1.25rem !important;
          border: 2px solid var(--border-default, #E4E4E7) !important;
          border-radius: 12px !important;
          background: var(--surface-input, #FFFFFF) !important;
          color: var(--text-primary, #18181B) !important;
          text-align: center !important;
          transition: border-color 0.2s ease !important;
        }

        .cl-otpCodeFieldInput:focus {
          border-color: var(--primary, #8B5CF6) !important;
          box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.1) !important;
          outline: none !important;
        }

        .cl-otpCodeField {
          gap: 8px !important;
          justify-content: center !important;
          flex-wrap: nowrap !important;
        }

        /* Verification step container needs proper spacing */
        .cl-signIn-verifyEmailAddress,
        .cl-signIn-verifyPhoneNumber {
          overflow: visible !important;
          min-height: 400px !important;
        }

        .cl-signIn-verifyEmailAddress .cl-form,
        .cl-signIn-verifyPhoneNumber .cl-form {
          gap: 16px !important;
        }

        /* Error messages */
        .cl-formFieldErrorText {
          color: var(--error, #EF4444) !important;
          font-size: 0.75rem !important;
          margin-top: 4px !important;
        }

        /* Hide "Secured by Clerk" and Clerk footer */
        .cl-internal-1dauvpw,
        .cl-internal-mxmka,
        [aria-label*="Clerk"],
        .cl-footerPages,
        .cl-footerPagesLink,
        .cl-footer,
        .cl-footerAction,
        .cl-footerActionLink,
        .cl-footerActionText {
          display: none !important;
        }

        /* Main internal content wrapper */
        .cl-main {
          padding: 0 !important;
        }

        /* Forgot password link */
        .cl-formFieldAction {
          color: var(--primary, #8B5CF6) !important;
          font-size: 0.875rem !important;
          font-weight: 600 !important;
        }

        .cl-formFieldAction:hover {
          text-decoration: underline !important;
        }
      `}} />

      <div className="w-full max-w-md bg-white md:bg-transparent rounded-3xl md:rounded-none p-4 md:p-0 mt-4 md:mt-0 shadow-xl md:shadow-none">
        {/* Tenant-aware branding above the form */}
        <div className="text-center mb-4 md:mb-6">
          <div className="bg-white rounded-full inline-flex items-center justify-center shadow-lg w-24 h-24 md:w-28 md:h-28 overflow-hidden">
            {branding.logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={branding.logoUrl}
                alt={branding.name}
                className="w-full h-full object-contain"
              />
            ) : (
              <Image
                src="/static/images/chesster-logo-v3.png"
                alt={branding.name}
                width={112}
                height={112}
                className="w-full h-full object-contain"
              />
            )}
          </div>
          <h1 className="text-2xl font-bold text-gray-800 mt-4">{heading}</h1>
          <p className="text-sm text-gray-500 mt-1">{t('auth.signInSubtitle')}</p>
        </div>

        <SignIn
          appearance={{
            layout: {
              socialButtonsPlacement: 'bottom',
              socialButtonsVariant: 'blockButton',
            },
            variables: {
              colorPrimary: branding.primaryColor || '#9333ea',
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
              card: 'shadow-none border-0 bg-white p-4 rounded-3xl',
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

        {/* Custom footer with sign-up link */}
        <div className="text-center mt-4">
          <span className="text-gray-400 text-sm">{t('auth.noAccount')} </span>
          <a href="/sign-up" className="text-purple-600 font-bold text-sm hover:underline">
            {t('common.signUp')}
          </a>
        </div>
      </div>

    </div>
  )
}
