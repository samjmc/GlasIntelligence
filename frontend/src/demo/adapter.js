import { loadTape, resolve, elapsedFor, NOT_RECORDED, TAPE_LOAD_FAILED } from './tape'
import { decodeDemoId } from './sessionId'

// Paths that fire on the Home page before the user has chosen a scenario
// (billing status check, session sidebar, history panel). These are expected
// to return NOT_RECORDED without triggering the watchdog overlay.
const PRE_PICKER_PATHS = [
  '/api/billing/status',
  '/api/session/active',
  '/api/simulation/history',
]

let activeScenario = null
let activeSessionId = null

// Rehydrate from the session id that Home.vue persists to localStorage under
// SESSION_KEY ('glas_active_session'). A page reload or deep link into a
// simulation route would otherwise leave activeScenario null, giving an
// infinite spinner with no watchdog overlay — which defeats the deliberate
// watchdog design.
if (typeof window !== 'undefined') {
  try {
    const stored = localStorage.getItem('glas_active_session')
    if (stored) {
      const decoded = decodeDemoId(stored)
      if (decoded?.scenario) {
        activeScenario = decoded.scenario
        activeSessionId = stored
      }
    }
  } catch {
    /* localStorage unavailable in SSR/test environments — safe to ignore */
  }
}

export function setActiveScenario(scenario, sessionId = null) {
  activeScenario = scenario
  activeSessionId = sessionId
}

function announceIfMissing(body, path) {
  if (body && body.error === NOT_RECORDED && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('demo:not-recorded', { detail: { path } }))
  }
  if (body && body.error === TAPE_LOAD_FAILED && typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('demo:tape-load-failed', { detail: { path } }))
  }
}

async function answer(method, url) {
  if (!activeScenario) {
    // No scenario chosen and none stored — only suppress the watchdog for the
    // small set of paths that legitimately fire on Home before the picker.
    const normUrl = String(url).split('?')[0]
    if (PRE_PICKER_PATHS.some((p) => normUrl === p || normUrl.endsWith(p))) {
      return { status: 200, body: { success: false, error: NOT_RECORDED, path: normUrl } }
    }
    // Any other path with no scenario is an unexpected call — fire the watchdog
    // so the blank-screen / spinner problem surfaces rather than silently spinning.
    const body = { success: false, error: NOT_RECORDED, path: normUrl }
    announceIfMissing(body, normUrl)
    return { status: 200, body }
  }
  const tape = await loadTape(activeScenario)
  const elapsed = elapsedFor(activeSessionId, Date.now())
  const result = resolve(tape.index, method, url, elapsed)
  announceIfMissing(result.body, url)
  return result
}

function loadFailureBody(url) {
  return { success: false, error: TAPE_LOAD_FAILED, path: url }
}

// Axios calls the adapter with a normalised config and expects a promise resolving
// to a full response object. Replacing the adapter rather than patching methods
// covers the config-object call form used in api/graph.js, keeps the existing
// response interceptor working, and guarantees nothing falls through to the vite
// dev proxy at localhost:5001 when a fixture is missing.
export async function demoAdapter(config) {
  const method = (config.method || 'get').toUpperCase()
  const url = config.url || ''

  let status, body
  try {
    ;({ status, body } = await answer(method, url))
  } catch {
    body = loadFailureBody(url)
    status = 200
    announceIfMissing(body, url)
  }

  return {
    data: body,
    status,
    statusText: 'OK',
    headers: {},
    config,
    request: null,
  }
}

export async function demoFetch(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase()

  let status, body
  try {
    ;({ status, body } = await answer(method, String(url)))
  } catch {
    body = loadFailureBody(String(url))
    status = 200
    announceIfMissing(body, String(url))
  }

  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}
