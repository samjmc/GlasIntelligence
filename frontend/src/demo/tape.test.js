import { describe, it, expect } from 'vitest'
import { normalisePath, indexEntries, resolve, NOT_RECORDED, canonicalQuery, elapsedFor, addSkipMs, getSkipMs, resetSkipMs } from './tape'
import { encodeDemoId } from './sessionId'
import synthetic from './fixtures/synthetic-tape.json'

describe('normalisePath', () => {
  it.each([
    ['/api/simulation/create', '/api/simulation/create'],
    ['/api/session/550e8400-e29b-41d4-a716-446655440000', '/api/session/:id'],
    ['/api/session/demo_MTc1NDY1MA_energy_ab12cd34', '/api/session/:id'],
    ['/api/graph/task/12345', '/api/graph/task/:id'],
    ['/api/graph/data/graph_abc123def456789?refresh=true', '/api/graph/data/:id'],
    // Regression: a long endpoint name is not an id.
    ['/api/simulation/suggest-followups', '/api/simulation/suggest-followups'],
    ['/api/billing/can-research', '/api/billing/can-research'],
  ])('normalises %s', (raw, expected) => {
    expect(normalisePath(raw)).toBe(expected)
  })

  // If this file and backend/app/middleware/demo_recorder.py disagree, the
  // recorded key and the requested key differ and every lookup misses. The
  // cases above are duplicated verbatim in
  // backend/tests/test_demo_recorder.py::test_normalise_path — change both or
  // neither.
  it('treats a demo session id as an id', () => {
    expect(normalisePath('/api/session/demo_a_b_c')).toBe('/api/session/:id')
  })
})

describe('resolve', () => {
  const index = indexEntries(synthetic.entries)

  it('returns the single entry for a static key regardless of time', () => {
    const a = resolve(index, 'POST', '/api/simulation/create', 0)
    const b = resolve(index, 'POST', '/api/simulation/create', 999999)
    expect(a.body.data.id).toBe('sim-synthetic-1')
    expect(b.body.data.id).toBe('sim-synthetic-1')
  })

  it('advances a progressive key with elapsed time', () => {
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 0).body.data.twitter_current_round).toBe(0)
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 10000).body.data.twitter_current_round).toBe(1)
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 20000).body.data.twitter_current_round).toBe(2)
  })

  it('returns the entry in force between snapshots, not the next one', () => {
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 9999).body.data.twitter_current_round).toBe(0)
    expect(resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 10001).body.data.twitter_current_round).toBe(1)
  })

  it('clamps past the end of the tape instead of throwing', () => {
    const r = resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', 10 ** 9)
    expect(r.body.data.runner_status).toBe('completed')
  })

  it('clamps before the start of the tape', () => {
    const r = resolve(index, 'GET', '/api/simulation/status/demo_a_b_c', -5000)
    expect(r.body.data.twitter_current_round).toBe(0)
  })

  it('returns a structured not-recorded response for an unknown path', () => {
    const r = resolve(index, 'GET', '/api/does/not/exist', 0)
    expect(r.status).toBe(200)
    expect(r.body.success).toBe(false)
    expect(r.body.error).toBe(NOT_RECORDED)
  })

  it('distinguishes methods on the same path', () => {
    const r = resolve(index, 'DELETE', '/api/simulation/create', 0)
    expect(r.body.error).toBe(NOT_RECORDED)
  })
})

describe('canonicalQuery', () => {
  it('returns empty string for a path with no query', () => {
    expect(canonicalQuery('/api/report/abc/agent-log')).toBe('')
  })

  it('returns the query string for a path with params', () => {
    expect(canonicalQuery('/api/report/abc/agent-log?from_line=0')).toBe('from_line=0')
  })

  it('sorts multiple params by key', () => {
    expect(canonicalQuery('/foo?z=1&a=2')).toBe('a=2&z=1')
  })

  it('matches the Python recorder byte-for-byte (quote_plus)', () => {
    // Python's urlencode: space -> '+', ! * ' ( ) percent-encoded.
    expect(canonicalQuery('/foo?key=hello world')).toBe('key=hello+world')
    expect(canonicalQuery('/foo?y=a!b*c&x=1')).toBe('x=1&y=a%21b%2Ac')
    expect(canonicalQuery('/foo?from_line=0&refresh=true')).toBe('from_line=0&refresh=true')
  })
})

describe('query-string disambiguation (agent-log cursor)', () => {
  const index = indexEntries(synthetic.entries)

  it('returns from_line=0 snapshot at t=0', () => {
    const r = resolve(index, 'GET', '/api/report/demo-report-1/agent-log?from_line=0', 0)
    expect(r.status).toBe(200)
    expect(r.body.data.logs).toHaveLength(1)
    expect(r.body.data.logs[0].action).toBe('report_start')
  })

  it('advances from_line=0 snapshot with elapsed time', () => {
    const r = resolve(index, 'GET', '/api/report/demo-report-1/agent-log?from_line=0', 6000)
    expect(r.body.data.logs).toHaveLength(2)
    expect(r.body.data.logs[1].action).toBe('planning_complete')
  })

  it('returns from_line=1 snapshot independently of from_line=0', () => {
    const r = resolve(index, 'GET', '/api/report/demo-report-1/agent-log?from_line=1', 6000)
    expect(r.body.data.logs).toHaveLength(1)
    expect(r.body.data.logs[0].action).toBe('planning_complete')
    expect(r.body.data.from_line).toBe(1)
  })

  it('falls back to stripped path when no query-specific entry exists', () => {
    // from_line=99 has no specific entry — should fall back to stripped-path key
    // The stripped key has all agent-log entries merged, returns the last at max time.
    const r = resolve(index, 'GET', '/api/report/demo-report-1/agent-log?from_line=99', 99999)
    // The fallback must not return NOT_RECORDED since the path IS in the tape.
    expect(r.body.error).not.toBe(NOT_RECORDED)
  })
})

describe('skip clock', () => {
  const id = encodeDemoId(1_000_000, 'energy-price-cap')

  it('elapsedFor starts at zero skip', () => {
    resetSkipMs()
    expect(elapsedFor(id, 2_000_000)).toBe(1_000_000)
  })

  it('addSkipMs advances the clock', () => {
    resetSkipMs()
    addSkipMs(5000)
    expect(elapsedFor(id, 2_000_000)).toBe(1_005_000)
  })

  it('never goes negative and clamps to zero', () => {
    resetSkipMs()
    addSkipMs(-99999)
    expect(getSkipMs()).toBe(0)
  })

  it('resetSkipMs clears the offset', () => {
    addSkipMs(10_000)
    resetSkipMs()
    expect(getSkipMs()).toBe(0)
    expect(elapsedFor(id, 2_000_000)).toBe(1_000_000)
  })
})
