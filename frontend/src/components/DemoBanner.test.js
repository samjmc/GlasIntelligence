import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import DemoBanner from './DemoBanner.vue'

// loadTape is mocked so skip-to-end never hits the network; the skip clock
// state (addSkipMs/getSkipMs/resetSkipMs) stays real via importOriginal.
vi.mock('../demo/tape', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, loadTape: vi.fn() }
})

const Stub = { template: '<div />' }

const routes = [
  { path: '/', name: 'Landing', component: Stub },
  { path: '/simulation/:id/start', name: 'SimulationRun', component: Stub },
  { path: '/report/:id', name: 'Report', component: Stub },
  { path: '/interaction/:id', name: 'Interaction', component: Stub },
]

const PATHS = {
  Landing: '/',
  SimulationRun: '/simulation/demo-synthetic-sim/start',
  Report: '/report/demo-synthetic-sim',
  Interaction: '/interaction/demo-synthetic-sim',
}

// All mounts must install the router: the component calls useRoute() in setup.
async function mountBanner(routeName) {
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push(PATHS[routeName])
  await router.isReady()
  return mount(DemoBanner, { global: { plugins: [router] } })
}

async function activateSession(startMs = Date.now()) {
  const adapter = await import('../demo/adapter')
  const { encodeDemoId } = await import('../demo/sessionId')
  adapter.setActiveScenario('synthetic', encodeDemoId(startMs, 'synthetic'))
}

// Adapter state is module-level and persists across tests in this file, so
// clear it before every test; tests opt back in via activateSession().
beforeEach(async () => {
  const adapter = await import('../demo/adapter')
  adapter.setActiveScenario(null)
})

afterEach(async () => {
  const tape = await import('../demo/tape')
  tape.resetSkipMs()
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('DemoBanner', () => {
  describe('walkthrough scoping', () => {
    it('does not render the banner on the Landing route even with a session', async () => {
      await activateSession()
      const wrapper = await mountBanner('Landing')

      expect(wrapper.findAll('[data-test="demo-banner"]')).toHaveLength(0)
    })

    it('does not render the banner on SimulationRun when there is no active session', async () => {
      const wrapper = await mountBanner('SimulationRun')

      expect(wrapper.findAll('[data-test="demo-banner"]')).toHaveLength(0)
    })

    it('renders the banner on SimulationRun with an active session', async () => {
      await activateSession()
      const wrapper = await mountBanner('SimulationRun')

      expect(wrapper.find('[data-test="demo-banner"]').exists()).toBe(true)
      expect(wrapper.text()).toContain('Demo — replaying a recorded simulation')
    })

    it('can be dismissed', async () => {
      await activateSession()
      const wrapper = await mountBanner('SimulationRun')
      expect(wrapper.find('[data-test="demo-banner"]').exists()).toBe(true)

      await wrapper.find('[data-test="banner-dismiss"]').trigger('click')

      expect(wrapper.find('[data-test="demo-banner"]').exists()).toBe(false)
    })
  })

  describe('skip controls', () => {
    it('skip advances the clock by one step', async () => {
      await activateSession()
      const wrapper = await mountBanner('SimulationRun')

      await wrapper.find('[data-test="demo-skip"]').trigger('click')

      const tape = await import('../demo/tape')
      expect(tape.getSkipMs()).toBe(90_000)
    })

    it('skip-to-end jumps the clock to the tape duration', async () => {
      const tape = await import('../demo/tape')
      const addSpy = vi.spyOn(tape, 'addSkipMs')
      vi.mocked(tape.loadTape).mockResolvedValue({ duration_ms: 900_000 })

      // Fixed now so wallBase is deterministic: the session was minted exactly
      // 60 s before Date.now(), so needed = duration/SPEEDUP - 60_000 - skip.
      const NOW = 1_800_000_000_000
      const nowSpy = vi.spyOn(Date, 'now').mockReturnValue(NOW)
      await activateSession(NOW - 60_000)

      const { DEMO_SPEEDUP } = await import('../demo/config')
      const expected = 900_000 / DEMO_SPEEDUP - 60_000

      const wrapper = await mountBanner('SimulationRun')
      await wrapper.find('[data-test="demo-skip-end"]').trigger('click')
      await flushPromises()

      expect(tape.loadTape).toHaveBeenCalledWith('synthetic')
      expect(addSpy).toHaveBeenCalledWith(expected)
      expect(tape.getSkipMs()).toBe(expected)
      expect(nowSpy).toHaveBeenCalled()
    })
  })

  describe('watchdog: demo:not-recorded', () => {
    it('shows not-recorded overlay when the event fires', async () => {
      const wrapper = await mountBanner('Landing')

      // Initially no error overlay
      expect(wrapper.find('[data-test="watchdog-not-recorded"]').exists()).toBe(false)

      // Fire the event
      window.dispatchEvent(new CustomEvent('demo:not-recorded', { detail: { path: '/api/run/status' } }))
      await flushPromises()

      // Error overlay appears
      expect(wrapper.find('[data-test="watchdog-not-recorded"]').exists()).toBe(true)
      // Text indicates which specific failure it is
      expect(wrapper.find('[data-test="watchdog-not-recorded"]').text()).toContain('not recorded')
    })

    it('removes the event listener on unmount to prevent stale handlers', async () => {
      const addSpy = vi.spyOn(window, 'addEventListener')
      const removeSpy = vi.spyOn(window, 'removeEventListener')

      const wrapper = await mountBanner('Landing')

      const addedCount = addSpy.mock.calls.filter(c => c[0] === 'demo:not-recorded').length
      expect(addedCount).toBeGreaterThan(0)

      wrapper.unmount()

      const removedCount = removeSpy.mock.calls.filter(c => c[0] === 'demo:not-recorded').length
      expect(removedCount).toBeGreaterThan(0)

      addSpy.mockRestore()
      removeSpy.mockRestore()
    })
  })

  describe('watchdog: demo:tape-load-failed', () => {
    it('shows tape-load-failed failure state when the event fires', async () => {
      const wrapper = await mountBanner('Landing')

      expect(wrapper.find('[data-test="watchdog-tape-failed"]').exists()).toBe(false)

      window.dispatchEvent(new CustomEvent('demo:tape-load-failed', { detail: { path: '/demo/energy-price-cap/tape.json' } }))
      await flushPromises()

      expect(wrapper.find('[data-test="watchdog-tape-failed"]').exists()).toBe(true)
      // Text indicates the different failure type
      expect(wrapper.find('[data-test="watchdog-tape-failed"]').text()).toContain('failed to load')
    })

    it('removes the tape-load-failed event listener on unmount', async () => {
      const removeSpy = vi.spyOn(window, 'removeEventListener')

      const wrapper = await mountBanner('Landing')
      wrapper.unmount()

      const removedCount = removeSpy.mock.calls.filter(c => c[0] === 'demo:tape-load-failed').length
      expect(removedCount).toBeGreaterThan(0)

      removeSpy.mockRestore()
    })
  })

  describe('watchdog: two conditions are distinguishable', () => {
    it('not-recorded and tape-load-failed show different UI elements', async () => {
      // not-recorded
      const wrapper1 = await mountBanner('Landing')
      window.dispatchEvent(new CustomEvent('demo:not-recorded', { detail: { path: '/api/foo' } }))
      await flushPromises()
      expect(wrapper1.find('[data-test="watchdog-not-recorded"]').exists()).toBe(true)
      expect(wrapper1.find('[data-test="watchdog-tape-failed"]').exists()).toBe(false)
      wrapper1.unmount()

      // tape-load-failed
      const wrapper2 = await mountBanner('Landing')
      window.dispatchEvent(new CustomEvent('demo:tape-load-failed', { detail: { path: '/demo/x/tape.json' } }))
      await flushPromises()
      expect(wrapper2.find('[data-test="watchdog-tape-failed"]').exists()).toBe(true)
      expect(wrapper2.find('[data-test="watchdog-not-recorded"]').exists()).toBe(false)
      wrapper2.unmount()
    })
  })
})
