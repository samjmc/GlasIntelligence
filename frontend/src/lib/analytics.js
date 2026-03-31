import posthog from 'posthog-js'

const POSTHOG_KEY = import.meta.env.VITE_POSTHOG_KEY
let initialized = false

export function initAnalytics() {
  if (!POSTHOG_KEY) return
  posthog.init(POSTHOG_KEY, {
    api_host: import.meta.env.VITE_POSTHOG_HOST || 'https://us.i.posthog.com',
    autocapture: false,
    capture_pageview: true,
    persistence: 'localStorage',
  })
  initialized = true
}

export function identifyUser(userId, properties = {}) {
  if (!initialized) return
  posthog.identify(userId, properties)
}

export function trackEvent(name, properties = {}) {
  if (!initialized) return
  posthog.capture(name, properties)
}
