import { describe, it, expect, vi, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// The run page said "Max simulation rounds: 40" while the run really did 10: Step 2 floored
// the configured rounds at 40 and passed that on. It must pass the rounds the config will
// run, and say when the environment is ready.

const api = vi.hoisted(() => ({
  prepareSimulation: vi.fn(),
  getPrepareStatus: vi.fn(),
  getSimulationProfilesRealtime: vi.fn(),
  getSimulationConfig: vi.fn(),
  getSimulationConfigRealtime: vi.fn(),
}))
vi.mock('../api/simulation', () => api)

import Step2EnvSetup from './Step2EnvSetup.vue'

// 10 simulated hours at 60 minutes a round is 10 rounds (the backend capped the config to this)
const cappedConfig = { time_config: { total_simulation_hours: 10, minutes_per_round: 60 } }

async function mountReady(userPlan) {
  api.prepareSimulation.mockResolvedValue({ success: true, data: { already_prepared: true } })
  api.getSimulationProfilesRealtime.mockResolvedValue({ success: true, data: { profiles: [] } })
  api.getSimulationConfigRealtime.mockResolvedValue({
    success: true,
    data: { config_generated: true, config: cappedConfig, summary: {} },
  })
  const wrapper = mount(Step2EnvSetup, {
    props: { simulationId: 'sim_x', userPlan, systemLogs: [] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

describe('Step2EnvSetup rounds', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it.each(['free', 'pro', 'business', 'enterprise'])('passes the configured 10 rounds, not 40, for a %s plan', async (plan) => {
    const wrapper = await mountReady(plan)
    await wrapper.find('[data-test="start-simulation"]').trigger('click')
    expect(wrapper.emitted('next-step')).toEqual([[{ maxRounds: 10 }]])
    wrapper.unmount()
  })

  it('shows the configured rounds in the enterprise custom slider', async () => {
    const wrapper = await mountReady('enterprise')
    await wrapper.find('.switch-control input').setValue(true)
    expect(wrapper.find('.slider-main-value .val-num').text()).toBe('10')
    expect(wrapper.text()).toContain('10 (recommended)')
    expect(wrapper.text()).not.toContain('40')
    wrapper.unmount()
  })
})

describe('Step2EnvSetup when the environment is ready', () => {
  afterEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('announces it, asks the page to show the panel, and focuses Start Simulation', async () => {
    const wrapper = await mountReady('pro')
    await flushPromises()

    expect(wrapper.find('[data-test="step-ready-message"]').text())
      .toBe('Environment ready. Next: start the simulation (10 rounds).')
    expect(wrapper.find('[data-test="step-ready-message"]').attributes('aria-live')).toBe('polite')
    expect(wrapper.emitted('step-ready')).toHaveLength(1)
    const btn = wrapper.find('[data-test="start-simulation"]')
    expect(btn.element.tagName).toBe('BUTTON')
    expect(document.activeElement).toBe(btn.element)
    wrapper.unmount()
  })
})
