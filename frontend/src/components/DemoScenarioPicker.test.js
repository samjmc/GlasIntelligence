import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DemoScenarioPicker from './DemoScenarioPicker.vue'

const manifest = {
  schema_version: 1,
  scenarios: [
    { id: 'energy-price-cap', title: 'Energy price cap', blurb: 'Retail cap effects.', prompt: 'Model a cap', duration_ms: 120000 },
  ],
}

beforeEach(() => {
  global.fetch = vi.fn(async () => ({ ok: true, status: 200, json: async () => manifest }))
})

describe('DemoScenarioPicker', () => {
  it('renders a card per scenario from the manifest', async () => {
    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    expect(wrapper.findAll('[data-test="scenario-card"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Energy price cap')
    expect(wrapper.text()).toContain('Retail cap effects.')
  })

  it('emits a demo session id and prompt when a card is clicked', async () => {
    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    await wrapper.find('[data-test="scenario-card"]').trigger('click')

    const [payload] = wrapper.emitted('select')[0]
    expect(payload.scenarioId).toBe('energy-price-cap')
    expect(payload.prompt).toBe('Model a cap')
    expect(payload.sessionId).toMatch(/^demo_/)
  })

  it('shows an error state when the manifest fails to load', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }))

    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    expect(wrapper.find('[data-test="picker-error"]').exists()).toBe(true)
  })

  it('shows a visible error and does not emit select when a scenario id contains an underscore', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: 1,
        scenarios: [
          { id: 'energy_price_cap', title: 'Energy price cap', blurb: 'Retail cap effects.', prompt: 'Model a cap', duration_ms: 120000 },
        ],
      }),
    }))

    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    await wrapper.find('[data-test="scenario-card"]').trigger('click')

    expect(wrapper.find('[data-test="picker-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="picker-error"]').text()).toContain('energy_price_cap')
    expect(wrapper.emitted('select')).toBeFalsy()
  })
})
