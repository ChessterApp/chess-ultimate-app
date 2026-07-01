'use client'

import { SignUp } from '@clerk/nextjs'
import { useTranslations } from 'next-intl'
import Image from 'next/image'
import { useSearchParams } from 'next/navigation'
import { useMemo } from 'react'
import { useBranding, useOrganization } from '@/contexts/OrganizationContext'

interface InvitePreview {
  firstName: string | null
  expired: boolean
}

/**
 * Decode an invite JWT *without* verifying the signature, only to extract
 * the first name for a warm "Welcome <Name>" greeting and to check `exp`.
 * The webhook re-verifies the signature server-side — never trust this for
 * any auth-relevant decision.
 */
function previewInvite(jwt: string | null): InvitePreview | null {
  if (!jwt) return null
  const parts = jwt.split('.')
  if (parts.length !== 3) return null
  try {
    const payload = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = payload + '='.repeat((4 - (payload.length % 4)) % 4)
    const json = atob(padded)
    const claims = JSON.parse(json) as {
      exp?: number
      first_name?: string
      student_first_name?: string
    }
    const now = Math.floor(Date.now() / 1000)
    return {
      firstName: claims.first_name ?? claims.student_first_name ?? null,
      expired: typeof claims.exp === 'number' && claims.exp < now,
    }
  } catch {
    return null
  }
}

export default function SignUpPage() {
  const t = useTranslations()
  const branding = useBranding()
  const { isWhiteLabel, org } = useOrganization()
  const searchParams = useSearchParams()
  const inviteJwt = searchParams?.get('invite') ?? null
  const invite = useMemo(() => previewInvite(inviteJwt), [inviteJwt])
  const isChessEmpire = org?.slug === 'chess-empire'
  const hasValidInvite = !!inviteJwt && invite !== null && !invite.expired

  const heading = isWhiteLabel
    ? `${t('auth.signUpTitle')} · ${branding.name}`
    : t('auth.signUpTitle')

  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)]">
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

        /* Hide Clerk header on initial step — show on verification */
        .cl-header:not(:has(+ * .cl-otpCodeFieldInput)):not(:has(~ * .cl-otpCodeFieldInput)) {
          display: none !important;
        }
        /* Show header when OTP verification is active */
        .cl-signUp-verifyEmailAddress .cl-header,
        .cl-signUp-verifyPhoneNumber .cl-header {
          display: block !important;
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

        /* Form field labels - hide on initial step, show on verification */
        .cl-formFieldLabel {
          display: none !important;
        }
        .cl-signUp-verifyEmailAddress .cl-formFieldLabel,
        .cl-signUp-verifyPhoneNumber .cl-formFieldLabel {
          display: block !important;
        }

        /* Form field wrapper - tight spacing like Duolingo */
        .cl-formFieldRow {
          margin-bottom: 4px !important;
        }

        /* Form container - reduce overall gaps */
        .cl-form {
          gap: 4px !important;
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
        .cl-signUp-verifyEmailAddress,
        .cl-signUp-verifyPhoneNumber {
          overflow: visible !important;
          min-height: 400px !important;
        }

        .cl-signUp-verifyEmailAddress .cl-form,
        .cl-signUp-verifyPhoneNumber .cl-form {
          gap: 16px !important;
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

        /* Form container */
        .cl-form {
          gap: 0 !important;
        }

        /* Error messages */
        .cl-formFieldErrorText {
          color: var(--error, #EF4444) !important;
          font-size: 0.75rem !important;
          margin-top: 4px !important;
        }

        /* Hide "Secured by Clerk" and all Clerk footers on initial step */
        .cl-internal-1dauvpw,
        .cl-internal-mxmka,
        [aria-label*="Clerk"],
        .cl-footerPages,
        .cl-footerPagesLink {
          display: none !important;
        }
        /* Hide footer on initial sign-up step */
        .cl-signUp-start .cl-footer,
        .cl-signUp-start .cl-footerAction,
        .cl-signUp-start .cl-footerActionText,
        .cl-signUp-start .cl-footerActionLink {
          display: none !important;
        }
        /* Show footer during verification (resend code link) */
        .cl-signUp-verifyEmailAddress .cl-footer,
        .cl-signUp-verifyPhoneNumber .cl-footer {
          display: block !important;
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
          color: var(--primary, #8B5CF6) !important;
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
          <p className="text-sm text-gray-500 mt-1">{t('auth.signUpSubtitle')}</p>
          {hasValidInvite && invite?.firstName && (
            <p data-testid="signup-invite-welcome" className="text-base font-semibold text-purple-600 mt-3">
              {t('welcome.signupWelcome', { firstName: invite.firstName })}
            </p>
          )}
        </div>

        {isChessEmpire && !hasValidInvite && (
          <div
            data-testid="signup-invite-missing-notice"
            className="mb-4 rounded-2xl border-2 border-purple-100 bg-purple-50 p-4 text-center"
          >
            <p className="text-sm text-purple-900">{t('welcome.signupNotice')}</p>
            <p className="text-xs text-purple-700 mt-1">{t('welcome.signupNoticeHint')}</p>
          </div>
        )}

        <SignUp
          {...(hasValidInvite && inviteJwt ? { unsafeMetadata: { inviteJwt } } : {})}
          appearance={{
            layout: {
              socialButtonsPlacement: 'bottom',
              socialButtonsVariant: 'blockButton',
              termsPageUrl: '/terms',
              privacyPageUrl: '/privacy',
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
              footerAction: '',
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
