import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DemoBanner from './DemoBanner.vue'

describe('DemoBanner', () => {
  it('renders the demo banner text', () => {
    const wrapper = mount(DemoBanner)
    expect(wrapper.text()).toContain('Demo — replaying a recorded simulation')
  })

  it('can be dismissed', async () => {
    const wrapper = mount(DemoBanner)
    expect(wrapper.find('[data-test="demo-banner"]').exists()).toBe(true)
    await wrapper.find('[data-test="banner-dismiss"]').trigger('click')
    expect(wrapper.find('[data-test="demo-banner"]').exists()).toBe(false)
  })

  describe('watchdog: demo:not-recorded', () => {
    it('shows not-recorded failure state and stops the run when the event fires', async () => {
      const wrapper = mount(DemoBanner)

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

      const wrapper = mount(DemoBanner)

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
      const wrapper = mount(DemoBanner)

      expect(wrapper.find('[data-test="watchdog-tape-failed"]').exists()).toBe(false)

      window.dispatchEvent(new CustomEvent('demo:tape-load-failed', { detail: { path: '/demo/energy-price-cap/tape.json' } }))
      await flushPromises()

      expect(wrapper.find('[data-test="watchdog-tape-failed"]').exists()).toBe(true)
      // Text indicates the different failure type
      expect(wrapper.find('[data-test="watchdog-tape-failed"]').text()).toContain('failed to load')
    })

    it('removes the tape-load-failed event listener on unmount', async () => {
      const removeSpy = vi.spyOn(window, 'removeEventListener')

      const wrapper = mount(DemoBanner)
      wrapper.unmount()

      const removedCount = removeSpy.mock.calls.filter(c => c[0] === 'demo:tape-load-failed').length
      expect(removedCount).toBeGreaterThan(0)

      removeSpy.mockRestore()
    })
  })

  describe('watchdog: two conditions are distinguishable', () => {
    it('not-recorded and tape-load-failed show different UI elements', async () => {
      // not-recorded
      const wrapper1 = mount(DemoBanner)
      window.dispatchEvent(new CustomEvent('demo:not-recorded', { detail: { path: '/api/foo' } }))
      await flushPromises()
      expect(wrapper1.find('[data-test="watchdog-not-recorded"]').exists()).toBe(true)
      expect(wrapper1.find('[data-test="watchdog-tape-failed"]').exists()).toBe(false)
      wrapper1.unmount()

      // tape-load-failed
      const wrapper2 = mount(DemoBanner)
      window.dispatchEvent(new CustomEvent('demo:tape-load-failed', { detail: { path: '/demo/x/tape.json' } }))
      await flushPromises()
      expect(wrapper2.find('[data-test="watchdog-tape-failed"]').exists()).toBe(true)
      expect(wrapper2.find('[data-test="watchdog-not-recorded"]').exists()).toBe(false)
      wrapper2.unmount()
    })
  })
})
