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
  removeSimulationAgents: vi.fn(),
}))
vi.mock('../api/simulation', () => api)

import Step2EnvSetup from './Step2EnvSetup.vue'

// 10 simulated hours at 60 minutes a round is 10 rounds (the backend capped the config to this)
const cappedConfig = { time_config: { total_simulation_hours: 10, minutes_per_round: 60 } }

async function mountReady(userPlan, profiles = []) {
  api.prepareSimulation.mockResolvedValue({ success: true, data: { already_prepared: true } })
  api.getSimulationProfilesRealtime.mockResolvedValue({ success: true, data: { profiles } })
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

// Some wrong agents get past the agent check in prepare (live: "O2", gone from Ireland since
// 2015), so the user removes them here before starting the run.
describe('Step2EnvSetup removing an agent before the start', () => {
  const people = [
    { user_id: 0, name: 'Vodafone Ireland', username: 'vodafone_ireland_101', bio: 'Telco' },
    { user_id: 1, name: 'O2', username: 'o2_102', bio: 'Telco' },
    { user_id: 2, name: 'ComReg', username: 'comreg_103', bio: 'Regulator' },
  ]
  const removeBtn = (wrapper, name) => wrapper.find(`button[aria-label="Remove agent ${name}"]`)

  afterEach(() => {
    document.body.innerHTML = ''
    vi.clearAllMocks()
  })

  it('gives every agent a real Remove button named after the agent', async () => {
    const wrapper = await mountReady('pro', people)
    for (const p of people) {
      const btn = removeBtn(wrapper, p.name)
      expect(btn.exists()).toBe(true)
      expect(btn.element.tagName).toBe('BUTTON')
      expect(btn.attributes('type')).toBe('button')
      expect(btn.attributes('disabled')).toBeUndefined()
    }
    wrapper.unmount()
  })

  it('asks to confirm and does not open the persona details', async () => {
    const wrapper = await mountReady('pro', people)
    await removeBtn(wrapper, 'O2').trigger('click')
    expect(wrapper.find('.profile-modal-overlay').exists()).toBe(false)
    expect(api.removeSimulationAgents).not.toHaveBeenCalled()
    const yes = wrapper.find('[data-test="confirm-remove-yes"]')
    expect(yes.attributes('aria-label')).toBe('Yes, remove O2')
    await flushPromises()
    expect(document.activeElement).toBe(yes.element)

    await wrapper.find('[data-test="confirm-remove-no"]').trigger('click')
    expect(wrapper.find('[data-test="confirm-remove-yes"]').exists()).toBe(false)
    expect(api.removeSimulationAgents).not.toHaveBeenCalled()
    expect(wrapper.find('.profile-modal-overlay').exists()).toBe(false)
    wrapper.unmount()
  })

  it('removes the agent on Yes, updates the list and counts, and announces it', async () => {
    const left = [people[0], { ...people[2], user_id: 1 }]
    const config = { ...cappedConfig, agent_configs: [{ agent_id: 0 }, { agent_id: 1 }] }
    api.removeSimulationAgents.mockResolvedValue({
      success: true, data: { removed: ['O2'], count: 2, profiles: left, config },
    })
    const wrapper = await mountReady('pro', people)
    await removeBtn(wrapper, 'O2').trigger('click')
    await wrapper.find('[data-test="confirm-remove-yes"]').trigger('click')
    await flushPromises()

    expect(api.removeSimulationAgents).toHaveBeenCalledWith('sim_x', { agent_ids: [1] })
    expect(wrapper.findAll('.profile-card')).toHaveLength(2)
    expect(removeBtn(wrapper, 'O2').exists()).toBe(false)
    expect(wrapper.find('.stats-grid .stat-value').text()).toBe('2')
    expect(wrapper.find('.config-block-badge').text()).toBe('2')
    const live = wrapper.find('[data-test="step-ready-message"]')
    expect(live.attributes('aria-live')).toBe('polite')
    expect(live.text()).toBe('Removed O2. 2 agents left.')
    wrapper.unmount()
  })

  it('disables removing and starting while the request is in flight', async () => {
    let finish
    api.removeSimulationAgents.mockReturnValue(new Promise((resolve) => { finish = resolve }))
    const wrapper = await mountReady('pro', people)
    await removeBtn(wrapper, 'O2').trigger('click')
    await wrapper.find('[data-test="confirm-remove-yes"]').trigger('click')

    expect(wrapper.find('[data-test="confirm-remove-yes"]').attributes('disabled')).toBeDefined()
    expect(removeBtn(wrapper, 'ComReg').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="start-simulation"]').attributes('disabled')).toBeDefined()
    await removeBtn(wrapper, 'ComReg').trigger('click')
    expect(api.removeSimulationAgents).toHaveBeenCalledTimes(1)

    finish({ success: true, data: { count: 2, profiles: [people[0], { ...people[2], user_id: 1 }] } })
    await flushPromises()
    expect(removeBtn(wrapper, 'ComReg').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it("shows the server's error and keeps the agent", async () => {
    api.removeSimulationAgents.mockRejectedValue(Object.assign(new Error('Request failed with status code 400'), {
      response: { status: 400, data: { success: false, error: 'A simulation needs at least 2 agents; removing 1 would leave 1' } },
    }))
    const wrapper = await mountReady('pro', people)
    await removeBtn(wrapper, 'O2').trigger('click')
    await wrapper.find('[data-test="confirm-remove-yes"]').trigger('click')
    await flushPromises()

    const error = wrapper.find('[data-test="remove-agent-error"]')
    expect(error.attributes('role')).toBe('alert')
    expect(error.text()).toBe('Could not remove O2: A simulation needs at least 2 agents; removing 1 would leave 1')
    expect(wrapper.findAll('.profile-card')).toHaveLength(3)
    expect(wrapper.find('[data-test="confirm-remove-yes"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('locks removal once the server says the simulation has started (409)', async () => {
    api.removeSimulationAgents.mockRejectedValue(Object.assign(new Error('409'), {
      response: { status: 409, data: { error: 'This simulation has already been started; its agents can no longer change' } },
    }))
    const wrapper = await mountReady('pro', people)
    await removeBtn(wrapper, 'O2').trigger('click')
    await wrapper.find('[data-test="confirm-remove-yes"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="remove-agent-error"]').text()).toContain('already been started')
    expect(removeBtn(wrapper, 'ComReg').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('disables Remove once the simulation is started', async () => {
    const wrapper = await mountReady('pro', people)
    await wrapper.find('[data-test="start-simulation"]').trigger('click')
    for (const p of people) {
      expect(removeBtn(wrapper, p.name).attributes('disabled')).toBeDefined()
    }
    await removeBtn(wrapper, 'O2').trigger('click')
    expect(wrapper.find('[data-test="confirm-remove-yes"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('still opens the persona details from the card', async () => {
    const wrapper = await mountReady('pro', people)
    await wrapper.findAll('.profile-card')[1].trigger('click')
    expect(wrapper.find('.profile-modal-overlay').exists()).toBe(true)
    wrapper.unmount()
  })
})
