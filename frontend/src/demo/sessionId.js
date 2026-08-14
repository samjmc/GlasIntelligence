// Demo session IDs are stateless: they carry the demo's start time and the chosen
// scenario, so a page reload resumes at the right point with no server involved.
// Format: demo_<b64url(start_ms)>_<scenario>_<nonce>

const PREFIX = 'demo_'

function b64urlEncode(str) {
  return btoa(str).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function b64urlDecode(str) {
  const padded = str.replace(/-/g, '+').replace(/_/g, '/')
  return atob(padded + '='.repeat((4 - (padded.length % 4)) % 4))
}

export function encodeDemoId(startMs, scenario) {
  // Scenario cannot contain '_' — it's used as the format delimiter.
  // If allowed, e.g. "energy_price_cap" would encode fine but decode to
  // the truncated name "energy" with no error, silently loading the wrong fixture.
  if (scenario.includes('_')) {
    throw new TypeError(`Scenario name cannot contain underscores; got: ${scenario}`)
  }
  const nonce = Math.random().toString(36).slice(2, 10)
  return `${PREFIX}${b64urlEncode(String(startMs))}_${scenario}_${nonce}`
}

export function decodeDemoId(id) {
  if (typeof id !== 'string' || !id.startsWith(PREFIX)) return null

  const parts = id.slice(PREFIX.length).split('_')
  if (parts.length < 3) return null

  const [encodedStart, scenario] = parts

  let startMs
  try {
    startMs = Number(b64urlDecode(encodedStart))
  } catch {
    return null
  }
  if (!Number.isFinite(startMs)) return null

  return { startMs, scenario }
}
