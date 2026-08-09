import { describe, it, expect, beforeEach, vi } from 'vitest'
import synthetic from './fixtures/synthetic-tape.json'

beforeEach(() => {
  vi.resetModules()
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
