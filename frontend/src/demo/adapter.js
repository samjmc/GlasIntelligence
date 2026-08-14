import { loadTape, resolve, elapsedFor, NOT_RECORDED, TAPE_LOAD_FAILED } from './tape'
import { decodeDemoId } from './sessionId'
import { SESSION_KEY } from './config'

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
    const stored = localStorage.getItem(SESSION_KEY)
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

// sessionId is required when a real run is in progress so elapsedFor() can
// advance the virtual clock correctly. Passing undefined (or omitting it)
// freezes the tape at t=0 — acceptable for tests that only check static
// single-entry responses, but callers should pass the actual session id for
// any test exercising time progression.
export function setActiveScenario(scenario, sessionId) {
  activeScenario = scenario
  activeSessionId = sessionId ?? null
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
// Serialise axios params object into a query string so that cursor-based
// endpoints (e.g. agent-log?from_line=N) reach answer() with their query
// string intact. Without this, config.url is just the path and all cursor
// values collapse onto the same stripped-key tape entry.
function buildUrl(config) {
  const base = config.url || ''
  const params = config.params
  if (!params || typeof params !== 'object') return base
  const qs = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&')
  return qs ? `${base}?${qs}` : base
}

export async function demoAdapter(config) {
  const method = (config.method || 'get').toUpperCase()
  const url = buildUrl(config)

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
