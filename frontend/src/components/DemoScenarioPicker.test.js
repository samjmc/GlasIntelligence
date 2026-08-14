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

  it('emits scenarioId and prompt (no sessionId) when a card is clicked', async () => {
    // The session id is intentionally NOT minted at picker-click: it is minted
    // at the moment startSimulation() fires so the virtual clock starts exactly
    // when the run begins. See IMPORTANT 2 in the final-review-fixes report.
    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    await wrapper.find('[data-test="scenario-card"]').trigger('click')

    const [payload] = wrapper.emitted('select')[0]
    expect(payload.scenarioId).toBe('energy-price-cap')
    expect(payload.prompt).toBe('Model a cap')
    expect(payload.sessionId).toBeUndefined()
  })

  it('shows an error state when the manifest fails to load', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }))

    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    expect(wrapper.find('[data-test="picker-error"]').exists()).toBe(true)
  })

  it('shows a visible error when the manifest schema_version does not match', async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ schema_version: 99, scenarios: [] }),
    }))

    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    expect(wrapper.find('[data-test="picker-error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="picker-error"]').text()).toContain('schema')
  })

  it('emits select even for scenario ids with underscores (underscore check moved to startSimulation)', async () => {
    // The underscore constraint is enforced by encodeDemoId(), which is now called
    // in Home.vue's startSimulation(), not in the picker. The picker's job is
    // only selecting a scenario; the error surfaces at run-start if the id is invalid.
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        schema_version: 1,
        scenarios: [
          { id: 'energy_price_cap', title: 'Energy price cap', blurb: 'Retail cap effects.', prompt: 'Model a cap' },
        ],
      }),
    }))

    const wrapper = mount(DemoScenarioPicker)
    await flushPromises()

    await wrapper.find('[data-test="scenario-card"]').trigger('click')

    // The picker emits the select event; startSimulation() will catch the TypeError.
    expect(wrapper.emitted('select')).toBeTruthy()
    expect(wrapper.find('[data-test="picker-error"]').exists()).toBe(false)
  })
})
