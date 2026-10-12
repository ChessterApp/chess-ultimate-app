import posthog from 'posthog-js'

// PostHog bootstrap. Events go through the first-party /ingest reverse proxy
// (next.config.ts rewrites) so ad blockers don't drop them. Kids' privacy:
// no IP, person profiles only for signed-in users, and session replay is off
// until PostHogRouteRecording starts it on allowlisted marketing/funnel routes.
const key = process.env.NEXT_PUBLIC_POSTHOG_KEY

if (key) {
  posthog.init(key, {
    api_host: '/ingest',
    ui_host: 'https://us.posthog.com',
    defaults: '2026-01-30',
    person_profiles: 'identified_only',
    property_denylist: ['$ip'],
    disable_session_recording: true,
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: '.ph-no-capture',
    },
  })
}
