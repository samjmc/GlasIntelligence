import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({ getSimulationHistory: vi.fn() }))
const push = vi.hoisted(() => vi.fn())

vi.mock('../api/simulation', () => api)
vi.mock('vue-router', () => ({ useRouter: () => ({ push }), useRoute: () => ({ path: '/' }) }))

import HistoryDatabase from './HistoryDatabase.vue'

const run = {
  simulation_id: 'sim_cb8bc9aa',
  project_id: 'proj_1',
  report_id: 'report_1',
  simulation_requirement: 'What if the US raises steel tariffs by 25%?',
  created_at: '2026-10-10T16:03:00',
  current_round: 3,
  total_rounds: 3,
  files: [],
}

async function mountHistory() {
  api.getSimulationHistory.mockResolvedValue({ success: true, data: [run] })
  const wrapper = mount(HistoryDatabase, { global: { stubs: { teleport: true } } })
  await flushPromises()
  return wrapper
}

describe('HistoryDatabase cards', () => {
  beforeEach(() => {
    // The component starts its observer on a 100 ms timer; fake timers keep it inside the test
    vi.useFakeTimers()
    vi.stubGlobal('IntersectionObserver', class { observe() {} disconnect() {} })
  })
  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('renders each card as a keyboard button that leads with the scenario', async () => {
    const wrapper = await mountHistory()
    const cards = wrapper.findAll('.project-card')
    expect(cards).toHaveLength(1)
    const card = cards[0]
    expect(card.attributes('role')).toBe('button')
    expect(card.attributes('tabindex')).toBe('0')
    expect(card.attributes('aria-label')).toBe(run.simulation_requirement)
    // The scenario comes before the small id line
    expect(card.element.firstElementChild.textContent).toBe(run.simulation_requirement)
    expect(card.find('.card-id').text()).toBe('SIM_CB8BC9')
    wrapper.unmount()
  })

  it('opens the detail modal on Enter, and offers chat for a finished report', async () => {
    const wrapper = await mountHistory()
    expect(wrapper.find('.modal-content').exists()).toBe(false)

    await wrapper.find('.project-card').trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('.modal-content').exists()).toBe(true)
    expect(wrapper.find('.hint-text').text()).toBe('Only the live simulation run (step 3) cannot be replayed')

    await wrapper.find('.btn-interaction').trigger('click')
    expect(push).toHaveBeenCalledWith({ name: 'Interaction', params: { reportId: 'report_1' } })
    wrapper.unmount()
  })

  it('opens the detail modal on Space too', async () => {
    const wrapper = await mountHistory()
    await wrapper.find('.project-card').trigger('keydown', { key: ' ' })
    expect(wrapper.find('.modal-content').exists()).toBe(true)
    wrapper.unmount()
  })
})
