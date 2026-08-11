import { describe, it, expect, beforeEach, vi } from 'vitest'
import synthetic from './fixtures/synthetic-tape.json'
import { encodeDemoId } from './sessionId'

// Helpers for setting up the localStorage mock used by the rehydration tests.
function mockLocalStorage(store = {}) {
  const storage = { ...store }
  global.localStorage = {
    getItem: (k) => storage[k] ?? null,
    setItem: (k, v) => { storage[k] = v },
    removeItem: (k) => { delete storage[k] },
  }
  return storage
}

beforeEach(() => {
  vi.resetModules()
  global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} }
  global.fetch = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => synthetic,
  }))
})

function makeFetchReject() {
  global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))
}

function makeFetchNonOk() {
  global.fetch = vi.fn(async () => ({ ok: false, status: 503 }))
}

describe('demoAdapter', () => {
  it('resolves with a valid axios response shape', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoAdapter({ url: '/api/simulation/create', method: 'post' })

    expect(res).toHaveProperty('data')
    expect(res).toHaveProperty('status', 200)
    expect(res).toHaveProperty('statusText')
    expect(res).toHaveProperty('headers')
    expect(res).toHaveProperty('config')
    expect(res.data.data.id).toBe('sim-synthetic-1')
  })

  it('defaults to GET when no method is given', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    // A UUID segment, so normalisePath collapses it to /api/session/:id.
    const res = await demoAdapter({ url: '/api/session/550e8400-e29b-41d4-a716-446655440000' })
    expect(res.data.data.prompt).toBe('synthetic scenario')
  })

  it('returns a not-recorded body rather than rejecting', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoAdapter({ url: '/api/nope', method: 'get' })
    expect(res.status).toBe(200)
    expect(res.data.success).toBe(false)
    expect(res.data.error).toBe('DEMO_NOT_RECORDED')
  })

  it('never issues a network request for an api path', async () => {
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    await demoAdapter({ url: '/api/simulation/create', method: 'post' })

    const urls = global.fetch.mock.calls.map((c) => c[0])
    expect(urls).toEqual(['/demo/synthetic/tape.json'])
  })
})

describe('demoAdapter tape-load failure', () => {
  it('resolves (does not reject) when fetch rejects', async () => {
    makeFetchReject()
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoAdapter({ url: '/api/simulation/create', method: 'post' })

    expect(res).toHaveProperty('data')
    expect(res).toHaveProperty('status', 200)
    expect(res.data.success).toBe(false)
    expect(res.data.error).toBe('DEMO_TAPE_LOAD_FAILED')
  })

  it('resolves (does not reject) when fetch returns non-ok after retry', async () => {
    makeFetchNonOk()
    const { demoAdapter, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoAdapter({ url: '/api/simulation/create', method: 'post' })

    expect(res).toHaveProperty('data')
    expect(res).toHaveProperty('status', 200)
    expect(res.data.success).toBe(false)
    expect(res.data.error).toBe('DEMO_TAPE_LOAD_FAILED')
  })
})

describe('adapter rehydration from localStorage', () => {
  it('picks up the active scenario from a stored demo session id on module load', async () => {
    const sessionId = encodeDemoId(Date.now(), 'synthetic')
    mockLocalStorage({ glas_active_session: sessionId })

    // Module is re-imported after vi.resetModules() so the init block runs fresh.
    const { demoAdapter } = await import('./adapter')

    // The rehydrated scenario is 'synthetic', so the tape fetch goes to the right path.
    const res = await demoAdapter({ url: '/api/simulation/create', method: 'post' })
    expect(res.data.data.id).toBe('sim-synthetic-1')

    const urls = global.fetch.mock.calls.map((c) => c[0])
    expect(urls).toEqual(['/demo/synthetic/tape.json'])
  })

  it('silently returns NOT_RECORDED for pre-picker paths when no scenario is stored', async () => {
    // No localStorage entry — simulates a first visit before the picker.
    const { demoAdapter } = await import('./adapter')

    const res = await demoAdapter({ url: '/api/billing/status', method: 'get' })
    expect(res.status).toBe(200)
    expect(res.data.error).toBe('DEMO_NOT_RECORDED')
    // Must not have attempted a tape fetch.
    expect(global.fetch).not.toHaveBeenCalled()
  })

  it('fires the watchdog for non-allowlisted paths when no scenario is stored', async () => {
    // Spy on jsdom's real window.dispatchEvent so we don't need to replace global.window
    // (deleting it after the test would destroy jsdom's window for every subsequent test).
    const dispatched = []
    const spy = vi.spyOn(window, 'dispatchEvent').mockImplementation((e) => {
      dispatched.push(e)
      return true
    })

    const { demoAdapter } = await import('./adapter')

    const res = await demoAdapter({ url: '/api/simulation/demo-e2e-sim', method: 'get' })
    expect(res.data.error).toBe('DEMO_NOT_RECORDED')
    expect(dispatched.some((e) => e.type === 'demo:not-recorded')).toBe(true)

    spy.mockRestore()
  })

  it('ignores a stored session id that is not a valid demo id', async () => {
    mockLocalStorage({ glas_active_session: 'regular-uuid-not-a-demo-id' })

    const { demoAdapter } = await import('./adapter')

    // With no valid demo id decoded, adapter behaves as if no scenario is set.
    const res = await demoAdapter({ url: '/api/billing/status', method: 'get' })
    expect(res.data.error).toBe('DEMO_NOT_RECORDED')
    expect(global.fetch).not.toHaveBeenCalled()
  })
})

describe('demoFetch tape-load failure', () => {
  it('resolves (does not reject) when fetch rejects', async () => {
    makeFetchReject()
    const { demoFetch, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoFetch('/api/simulation/create', { method: 'POST' })

    expect(res).toHaveProperty('ok')
    expect(res).toHaveProperty('status', 200)
    const body = await res.json()
    expect(body.success).toBe(false)
    expect(body.error).toBe('DEMO_TAPE_LOAD_FAILED')
  })

  it('resolves (does not reject) when fetch returns non-ok after retry', async () => {
    makeFetchNonOk()
    const { demoFetch, setActiveScenario } = await import('./adapter')
    setActiveScenario('synthetic')

    const res = await demoFetch('/api/simulation/create', { method: 'POST' })

    expect(res).toHaveProperty('ok')
    expect(res).toHaveProperty('status', 200)
    const body = await res.json()
    expect(body.success).toBe(false)
    expect(body.error).toBe('DEMO_TAPE_LOAD_FAILED')
  })
})
