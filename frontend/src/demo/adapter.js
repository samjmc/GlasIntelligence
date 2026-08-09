import { loadTape, resolve, elapsedFor, NOT_RECORDED, TAPE_LOAD_FAILED } from './tape'

let activeScenario = null
let activeSessionId = null

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
