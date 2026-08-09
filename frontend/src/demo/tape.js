// Must stay behaviourally identical to normalise_path() in
// backend/app/middleware/demo_recorder.py. If one changes, change the other.
// Shared test cases are duplicated verbatim in
// backend/tests/test_demo_recorder.py::test_normalise_path — change both or neither.

import { decodeDemoId } from './sessionId'
import { DEMO_SPEEDUP } from './config'

export const NOT_RECORDED = 'DEMO_NOT_RECORDED'
export const TAPE_LOAD_FAILED = 'DEMO_TAPE_LOAD_FAILED'
export const SCHEMA_VERSION = 1

// A path segment is an ID if it is a UUID, a demo id, an all-digit id, or a long
// opaque token. The opaque rule requires at least one digit: without it
// "/api/simulation/suggest-followups" (17 chars, no digits) would be treated as
// an id and merged with sibling endpoints.
// NOTE: DEMO must be /^demo[_-]/ (anchored at start only) — an unanchored match
// would hit mid-string and diverge from the Python counterpart.
const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/
const DEMO = /^demo[_-]/
const DIGITS = /^\d+$/
const OPAQUE = /^(?=.*\d)[A-Za-z0-9_-]{16,}$/

export function normalisePath(path) {
  return path
    .split('?')[0]
    .split('/')
    .map((seg) =>
      seg && (UUID.test(seg) || DEMO.test(seg) || DIGITS.test(seg) || OPAQUE.test(seg))
        ? ':id'
        : seg,
    )
    .join('/')
}

function keyFor(method, normalisedPath) {
  return `${method.toUpperCase()} ${normalisedPath}`
}

export function indexEntries(entries) {
  const index = new Map()
  for (const entry of entries) {
    const key = keyFor(entry.method, entry.path)
    if (!index.has(key)) index.set(key, [])
    index.get(key).push(entry)
  }
  for (const list of index.values()) list.sort((a, b) => a.t_ms - b.t_ms)
  return index
}

export function resolve(index, method, path, elapsedMs) {
  const list = index.get(keyFor(method, normalisePath(path)))

  if (!list || list.length === 0) {
    return {
      status: 200,
      body: { success: false, error: NOT_RECORDED, path: normalisePath(path) },
    }
  }

  // One recorded entry means the response never varied: return it whenever asked.
  if (list.length === 1) return { status: list[0].status, body: list[0].body }

  // Otherwise return the snapshot in force at elapsedMs, clamping at both ends.
  // Clamping is load-bearing: polling code in the app self-terminates only when
  // it sees the terminal response, so running off the end of the tape must never
  // throw or produce undefined.
  let chosen = list[0]
  for (const entry of list) {
    if (entry.t_ms <= elapsedMs) chosen = entry
    else break
  }
  return { status: chosen.status, body: chosen.body }
}

export function elapsedFor(sessionId, now = Date.now()) {
  const decoded = decodeDemoId(sessionId)
  if (!decoded) return 0
  return (now - decoded.startMs) * DEMO_SPEEDUP
}

const cache = new Map()

export async function loadTape(scenario) {
  if (cache.has(scenario)) return cache.get(scenario)

  const promise = (async () => {
    // One retry: a CDN hiccup on a static asset is usually transient, and the
    // alternative is a dead demo. A second failure is real and must surface.
    let res
    try {
      res = await fetch(`/demo/${scenario}/tape.json`)
      if (!res.ok) throw new Error(String(res.status))
    } catch {
      res = await fetch(`/demo/${scenario}/tape.json`)
    }
    if (!res.ok) throw new Error(`Demo tape for "${scenario}" failed to load (${res.status})`)

    const tape = await res.json()
    if (tape.schema_version !== SCHEMA_VERSION) {
      throw new Error(
        `Demo tape schema ${tape.schema_version} does not match expected ${SCHEMA_VERSION}`,
      )
    }

    tape.index = indexEntries(tape.entries)
    return tape
  })()

  // Evict on failure so a transient error does not poison the cache for the
  // lifetime of the page.
  promise.catch(() => cache.delete(scenario))

  cache.set(scenario, promise)
  return promise
}
