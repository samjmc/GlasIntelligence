import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import LandingView from './LandingView.vue'

// The demo section is build-time gated by isDemoMode; force it on in the test
// env so the boxes render. The real adapter/sessionId/tape modules are used.
vi.mock('../demo/config', () => ({ isDemoMode: true, SESSION_KEY: 'glas_active_session', DEMO_SPEEDUP: 1 }))

import { getActiveSessionId } from '../demo/adapter'
import { decodeDemoId } from '../demo/sessionId'

const manifest = {
  schema_version: 1,
  scenarios: [
    { id: 'pharmacy-first-caps', title: 'Pharmacy First funding caps', blurb: 'b', prompt: 'p' },
    { id: 'energy-price-cap', title: 'Energy price cap', blurb: 'b', prompt: 'p' },
  ],
}

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Landing', component: { template: '<div />' } },
      { path: '/simulation/:simulationId/start', name: 'SimulationRun', component: { template: '<div />' } },
      // Landing template links — stubbed so router-link resolves without warnings.
      { path: '/signup', name: 'Signup', component: { template: '<div />' } },
      { path: '/feed', name: 'Feed', component: { template: '<div />' } },
      { path: '/pricing', name: 'Pricing', component: { template: '<div />' } },
      { path: '/login', name: 'Login', component: { template: '<div />' } },
    ],
  })
}

function okFetch(body) {
  return vi.fn(async () => ({ ok: true, status: 200, json: async () => body }))
}

// Bare localStorage is unavailable in this test env (Node's experimental
// global shadows jsdom's) — stub it, same as adapter.test.js does.
function mockLocalStorage(store = {}) {
  const storage = { ...store }
  global.localStorage = {
    getItem: (k) => storage[k] ?? null,
    setItem: (k, v) => { storage[k] = v },
    removeItem: (k) => { delete storage[k] },
  }
}

let router

beforeEach(() => {
  mockLocalStorage()
  router = makeRouter()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LandingView demo boxes', () => {
  it('renders one demo-box per manifest scenario inside the feed section', async () => {
    vi.stubGlobal('fetch', okFetch(manifest))
    const wrapper = mount(LandingView, { global: { plugins: [router] } })
    await flushPromises()

    // The Worked-examples section is gone; the boxes now live in the feed section.
    expect(wrapper.find('[data-test="demo-section"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Worked examples')
    expect(wrapper.find('.feed-preview').text()).toContain('Latest Industry Intelligence')
    expect(wrapper.find('[data-test="demo-box-error"]').exists()).toBe(false)

    const boxes = wrapper.findAll('[data-test="demo-box"]')
    expect(boxes).toHaveLength(2)
    expect(boxes[0].attributes('data-scenario-id')).toBe('pharmacy-first-caps')
    expect(boxes[1].attributes('data-scenario-id')).toBe('energy-price-cap')
    expect(boxes[0].text()).toContain('Pharmacy First funding caps')
    expect(boxes[1].text()).toContain('Energy price cap')

    // In demo mode the static feed is replaced by the manifest scenarios.
    expect(wrapper.text()).not.toContain('Basel IV')
  })

  it('renders demo-box-error when the manifest fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) })))
    const wrapper = mount(LandingView, { global: { plugins: [router] } })
    await flushPromises()

    expect(wrapper.find('[data-test="demo-box-error"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="demo-box"]')).toHaveLength(0)
    expect(wrapper.find('[data-test="demo-box-error"]').text()).toContain('manifest')
  })

  it('launches the walkthrough directly when a box is clicked', async () => {
    vi.stubGlobal('fetch', okFetch(manifest))
    const wrapper = mount(LandingView, { global: { plugins: [router] } })
    await flushPromises()

    await wrapper.find('[data-test="demo-box"][data-scenario-id="pharmacy-first-caps"]').trigger('click')
    await flushPromises()

    // Session id minted at click-time and persisted so adapter.js can rehydrate.
    const stored = localStorage.getItem('glas_active_session')
    expect(stored).toBeTruthy()
    expect(decodeDemoId(stored)).toMatchObject({ scenario: 'pharmacy-first-caps' })
    expect(getActiveSessionId()).toBe(stored)

    // Navigates straight to the replay with no intermediate picker/start steps.
    expect(router.currentRoute.value.fullPath).toBe('/simulation/demo-pharmacy-first-caps-sim/start')
  })
})
